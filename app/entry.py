"""
Giao diện nhập liệu (máy A) — `make entry`, mở http://<máy A>:8080

- Thêm lượt đặt phòng (đối tượng chính) + dòng req_* tương ứng (dòng phụ thuộc), kể cả lượt đặt
  liên vùng (đoàn tour đã có phòng ở vùng khác). Chọn guest_type thì hiện đúng trường của loại đó.
- Trạm đích = vùng của khách sạn chứa phòng (đúng thiết kế phân mảnh dẫn xuất). Ghi THẲNG vào trạm
  đó (không qua postgres_fdw). booking.request (jsonb) và bản quan hệ req_* ghi trong MỘT giao dịch.
- Đồng thời ghi bản sao vào CSDL đối chứng bằng commit hai pha (PREPARE TRANSACTION) để đối chứng
  luôn khớp hệ phân tán (make check vẫn đạt sau khi nhập).
- Trạm đích mất kết nối => báo lỗi, KHÔNG ghi sang trạm khác.
- Thêm đoàn tour (bảng sao chép): 2PC ra cả 4 trạm + đối chứng; thiếu một trạm là huỷ.
- Thêm phòng mới vào một khách sạn; nút "thêm ngẫu nhiên N lượt đặt".
"""
import datetime as dt, json, random, time, uuid
from web import CSS, UserError, serve
import cfg
from cfg import CENTRAL, REGION_VN, SITES, connect, connect_ref, site
from pgwire import lit

WEIGHTS = [0.20, 0.26, 0.24, 0.30]
TYPES, TYPE_MIX = ["tour", "business", "family"], [0.45, 0.35, 0.20]


class SiteDown(UserError):
    pass


def open_site(s):
    i = site(s)
    try:
        return connect(s, connect_timeout=2, timeout=15, app="entry")
    except OSError as e:
        raise SiteDown(f"Trạm {s} (máy {i['machine']}, {i['ip']}:{i['port']}) MẤT KẾT NỐI — không ghi. "
                       f"Dữ liệu KHÔNG được ghi sang trạm khác. ({e})")


def where(s):
    i = site(s)
    return {"site": s, "region": REGION_VN[s], "machine": i["machine"], "ip": i["ip"], "port": i["port"]}


# ---------------------------------------------------------------- SQL dựng dòng
def group_code(tg):
    return f"TG{tg:04d}"


def booking_sql(b):
    """b: dict đã chuẩn hoá. Trả về các câu INSERT (booking + req_*), jsonb và bản quan hệ khớp nhau."""
    t = b["guest_type"]
    if t == "tour":
        req = {"group_code": group_code(b["tour_group_id"]), "meal_plan": b["meal_plan"], "guide_room": b["guide_room"]}
    elif t == "business":
        req = {"company": b["company"], "tax_code": b["tax_code"], "late_checkout": b["late_checkout"]}
    else:
        req = {"extra_bed": b["extra_bed"], "children_ages": b["children_ages"], "airport_pickup": b["airport_pickup"]}
    sql = [f"INSERT INTO booking (booking_id, room_id, guest_name, check_in, nights, guest_type, tour_group_id, request) "
           f"VALUES ({b['booking_id']}, {b['room_id']}, {lit(b['guest_name'])}, {lit(b['check_in'])}, {b['nights']}, "
           f"{lit(t)}, {lit(b.get('tour_group_id') if t == 'tour' else None)}, {lit(json.dumps(req, ensure_ascii=False))}::jsonb)"]
    if t == "tour":
        sql.append(f"INSERT INTO req_tour VALUES ({b['booking_id']}, {lit(req['group_code'])}, {lit(req['meal_plan'])}, {lit(req['guide_room'])})")
    elif t == "business":
        sql.append(f"INSERT INTO req_business VALUES ({b['booking_id']}, {lit(req['company'])}, {lit(req['tax_code'])}, {lit(req['late_checkout'])})")
    else:
        sql.append(f"INSERT INTO req_family VALUES ({b['booking_id']}, {lit(req['extra_bed'])}, {lit(req['airport_pickup'])})")
        for k, a in enumerate(req["children_ages"], 1):
            sql.append(f"INSERT INTO req_family_child VALUES ({b['booking_id']}, {k}, {int(a)})")
    return sql


def two_phase(targets, stmts, tag):
    """targets: list[(nhãn, kết nối)]. Ghi cùng một nhóm câu lệnh vào mọi đích bằng 2PC."""
    prepared = []
    try:
        for name, c in targets:
            gid = f"{tag}_{name}_{uuid.uuid4().hex[:8]}"
            c.execute("BEGIN;\n" + ";\n".join(stmts) + f";\nPREPARE TRANSACTION '{gid}'")
            prepared.append((c, gid))
    except Exception:
        for c, gid in prepared:
            try:
                c.execute(f"ROLLBACK PREPARED '{gid}'")
            except Exception:  # noqa: BLE001
                pass
        raise
    for c, gid in prepared:
        c.execute(f"COMMIT PREPARED '{gid}'")


def write_bookings(s, items, conn=None):
    """Ghi danh sách lượt đặt vào trạm s (một giao dịch) + đối chứng, bằng 2PC. Trả về danh sách mã."""
    own = conn is None
    c = conn or open_site(s)
    try:
        _, rows = c.query(f"SELECT nextval('booking_id_seq') FROM generate_series(1, {len(items)})")
        stmts = []
        for b, (bid,) in zip(items, rows):
            b["booking_id"] = bid
            stmts += booking_sql(b)
        with connect_ref(connect_timeout=2, timeout=15) as ref:
            two_phase([(s, c), ("ref", ref)], stmts, "bk")
        return [b["booking_id"] for b in items]
    finally:
        if own:
            c.close()


def group_regions(tg):
    out = {}
    for s in SITES:
        try:
            with connect(s, connect_timeout=1, timeout=5) as c:
                out[s] = c.scalar(f"SELECT count(*) FROM booking WHERE tour_group_id = {int(tg)}")
        except OSError:
            out[s] = None
    return out


# ---------------------------------------------------------------- API
def api_sites(_):
    return [where(s) | {"central": site(s)["central"]} for s in SITES]


def api_rooms(q):
    s = q.get("site")
    if s not in SITES:
        raise UserError("site không hợp lệ")
    with open_site(s) as c:
        _, hotels = c.query("SELECT hotel_id, name, stars FROM hotel ORDER BY hotel_id")
        _, rooms = c.query("SELECT r.room_id, r.hotel_id, r.room_type_code, t.name, t.capacity, r.floor, r.rate "
                           "FROM room r JOIN room_type t USING (room_type_code) ORDER BY r.hotel_id, r.room_id")
        _, rtypes = c.query("SELECT room_type_code, name, capacity FROM room_type ORDER BY 1")
    return {"hotels": hotels, "rooms": rooms, "room_types": rtypes, **where(s)}


def api_groups(_):
    with open_site(CENTRAL) as c:
        _, rows = c.query("SELECT tour_group_id, agency, size, start_date FROM tour_group ORDER BY tour_group_id DESC")
    return rows


def api_group_regions(q):
    return group_regions(int(q["tg"]))


def norm_booking(p):
    s = p.get("site")
    if s not in SITES:
        raise UserError("Chọn vùng (trạm) hợp lệ")
    t = p.get("guest_type")
    if t not in TYPES:
        raise UserError("guest_type phải là tour/business/family")
    try:
        b = {"room_id": int(p["room_id"]), "guest_name": (p.get("guest_name") or "").strip(),
             "check_in": dt.date.fromisoformat(p["check_in"]).isoformat(), "nights": int(p["nights"]), "guest_type": t}
    except (KeyError, ValueError) as e:
        raise UserError(f"Thiếu/sai trường: {e}")
    if not b["guest_name"]:
        raise UserError("Nhập tên khách")
    if not 1 <= b["nights"] <= 60:
        raise UserError("Số đêm 1–60")
    if t == "tour":
        if not p.get("tour_group_id"):
            raise UserError("Khách đoàn phải chọn đoàn tour")
        b |= {"tour_group_id": int(p["tour_group_id"]), "meal_plan": p.get("meal_plan", "BB"), "guide_room": bool(p.get("guide_room"))}
        if b["meal_plan"] not in ("BB", "HB", "FB"):
            raise UserError("meal_plan phải là BB/HB/FB")
    elif t == "business":
        b |= {"company": (p.get("company") or "").strip(), "tax_code": (p.get("tax_code") or "").strip(),
              "late_checkout": bool(p.get("late_checkout"))}
        if not b["company"] or not b["tax_code"]:
            raise UserError("Nhập công ty và mã số thuế")
    else:
        ages = [int(x) for x in str(p.get("children_ages") or "").replace(";", ",").split(",") if x.strip()]
        if any(a < 0 or a > 17 for a in ages):
            raise UserError("Tuổi trẻ em 0–17")
        b |= {"extra_bed": bool(p.get("extra_bed")), "airport_pickup": bool(p.get("airport_pickup")), "children_ages": ages}
    return s, b


def api_booking(p):
    s, b = norm_booking(p)
    before = group_regions(b["tour_group_id"]) if b["guest_type"] == "tour" else None
    t0 = time.perf_counter()
    try:
        bid = write_bookings(s, [b])[0]
    except SiteDown:
        raise
    except Exception as e:  # noqa: BLE001  (vi phạm khoá ngoại, CHECK, ... => báo nguyên văn)
        raise UserError(f"Trạm {s} từ chối ghi: {e}")
    ms = (time.perf_counter() - t0) * 1000
    res = {"ok": True, "booking_id": bid, "ms": round(ms, 1), **where(s)}
    if before is not None:
        others = [r for r, n in before.items() if n and r != s]
        res["cross_region"] = bool(others)
        res["group_regions_before"] = before
        res["note"] = (f"LIÊN VÙNG: đoàn {b['tour_group_id']} đã có phòng ở {', '.join(others)} — Q3 của đoàn này phải đọc "
                       f"{len(set(others) | {s})} trạm." if others else "Đoàn chưa có phòng ở vùng khác.")
    return res


def api_tour_group(p):
    try:
        agency, size = (p.get("agency") or "").strip(), int(p.get("size"))
        start = dt.date.fromisoformat(p.get("start_date")).isoformat()
    except (TypeError, ValueError):
        raise UserError("Nhập đủ công ty lữ hành, số người, ngày khởi hành")
    if not agency or size <= 0:
        raise UserError("Công ty lữ hành và số người > 0")
    conns = []
    try:
        for s in SITES:  # bảng SAO CHÉP: thiếu một trạm là không ghi
            conns.append((s, open_site(s)))
        tg = conns[[x[0] for x in conns].index(CENTRAL)][1].scalar("SELECT nextval('tour_group_id_seq')")
        stmt = [f"INSERT INTO tour_group VALUES ({tg}, {lit(agency)}, {size}, {lit(start)})"]
        with connect_ref(connect_timeout=2, timeout=15) as ref:
            two_phase(conns + [("ref", ref)], stmt, "tg")
    finally:
        for _, c in conns:
            c.close()
    return {"ok": True, "tour_group_id": tg, "group_code": group_code(tg), "sites": SITES,
            "note": "Đã ghi vào cả 4 trạm + đối chứng bằng commit hai pha (bảng sao chép)."}


def api_room(p):
    s = p.get("site")
    if s not in SITES:
        raise UserError("site không hợp lệ")
    try:
        hid, code, floor, rate = int(p["hotel_id"]), p["room_type_code"], int(p["floor"]), int(p["rate"])
    except (KeyError, ValueError):
        raise UserError("Nhập đủ khách sạn, loại phòng, tầng, giá")
    with open_site(s) as c:
        rid = c.scalar("SELECT nextval('room_id_seq')")
        with connect_ref(connect_timeout=2, timeout=15) as ref:
            two_phase([(s, c), ("ref", ref)],
                      [f"INSERT INTO room VALUES ({rid}, {hid}, {lit(code)}, {floor}, {rate})"], "rm")
    return {"ok": True, "room_id": rid, **where(s)}


NAMES_HO = ["Nguyễn", "Trần", "Lê", "Phạm", "Hoàng", "Võ", "Đặng", "Bùi"]
NAMES = ["Văn An", "Thị Lan", "Minh Huy", "Ngọc Mai", "Quốc Bảo", "Thu Hà", "Gia Khang", "Mỹ Linh"]


def api_random(p):
    n = max(1, min(int(p.get("n", 100)), 5000))
    rnd = random.Random()
    with open_site(CENTRAL) as c:
        groups = [r[0] for r in c.query("SELECT tour_group_id FROM tour_group")[1]]
    plan = {s: [] for s in SITES}
    for _ in range(n):
        s = rnd.choices(SITES, WEIGHTS)[0]
        t = rnd.choices(TYPES, TYPE_MIX)[0]
        b = {"guest_type": t, "guest_name": f"{rnd.choice(NAMES_HO)} {rnd.choice(NAMES)}",
             "check_in": (dt.date(2025, 1, 1) + dt.timedelta(days=rnd.randrange(546))).isoformat(),
             "nights": rnd.randint(1, 7)}
        if t == "tour":
            b |= {"tour_group_id": rnd.choice(groups), "meal_plan": rnd.choice(["BB", "HB", "FB"]), "guide_room": rnd.random() < 0.1}
        elif t == "business":
            b |= {"company": "Cty TNHH Ngẫu Nhiên", "tax_code": f"03{rnd.randint(10000000, 99999999)}", "late_checkout": rnd.random() < 0.3}
        else:
            b |= {"extra_bed": rnd.random() < 0.4, "airport_pickup": rnd.random() < 0.5,
                  "children_ages": [rnd.randint(0, 15) for _ in range(rnd.randint(0, 3))]}
        plan[s].append(b)
    out, t0 = [], time.perf_counter()
    for s, items in plan.items():
        if not items:
            continue
        try:
            with open_site(s) as c:
                rooms = [r[0] for r in c.query("SELECT room_id FROM room")[1]]
                for b in items:
                    b["room_id"] = rnd.choice(rooms)
                ids = write_bookings(s, items, conn=c)
            out.append({**where(s), "ok": True, "count": len(ids), "first_id": ids[0], "last_id": ids[-1]})
        except Exception as e:  # noqa: BLE001
            out.append({**where(s), "ok": False, "count": 0, "error": str(e)})
    return {"ok": all(x["ok"] for x in out), "requested": n, "written": sum(x["count"] for x in out),
            "per_site": out, "ms": round((time.perf_counter() - t0) * 1000, 1)}


PAGE = """<!doctype html><html lang="vi"><meta charset="utf-8"><title>Nhập liệu — Đề 6 Khách sạn</title>
<style>""" + CSS + """</style>
<header><h1>Nhập liệu · Chuỗi khách sạn nghỉ dưỡng</h1><span>ghi thẳng vào trạm của vùng khách sạn · CS5104 Đề 6</span></header>
<main>
<div class="grid g2">
<div class="card"><h2>1. Thêm lượt đặt phòng (booking + req_*)</h2>
  <div class="grid g2">
    <div><label>Vùng = trạm đích</label><select id="site"></select><div id="siteinfo" class="muted"></div></div>
    <div><label>Khách sạn</label><select id="hotel"></select></div>
  </div>
  <label>Phòng</label><select id="room"></select>
  <div class="grid g3">
    <div><label>Tên khách</label><input id="guest_name" value="Nguyễn Văn An"></div>
    <div><label>Ngày nhận phòng</label><input id="check_in" type="date" value="2025-07-10"></div>
    <div><label>Số đêm</label><input id="nights" type="number" value="2" min="1"></div>
  </div>
  <label>Loại khách (guest_type → dạng jsonb)</label>
  <select id="guest_type"><option value="tour">tour — khách đoàn</option><option value="business">business — công tác</option><option value="family">family — gia đình</option></select>
  <div id="f_tour" class="ft">
    <div class="grid g2"><div><label>Đoàn tour</label><select id="tour_group_id"></select></div>
    <div><label>Gói ăn (meal_plan)</label><select id="meal_plan"><option>BB</option><option>HB</option><option>FB</option></select></div></div>
    <div class="chk"><input type="checkbox" id="guide_room"> Có phòng cho hướng dẫn viên (guide_room)</div>
    <div id="groupinfo" class="muted"></div>
  </div>
  <div id="f_business" class="ft" hidden>
    <div class="grid g2"><div><label>Công ty</label><input id="company" value="Cty TNHH Minh Long"></div>
    <div><label>Mã số thuế</label><input id="tax_code" value="0312345678"></div></div>
    <div class="chk"><input type="checkbox" id="late_checkout"> Trả phòng muộn (late_checkout)</div>
  </div>
  <div id="f_family" class="ft" hidden>
    <label>Tuổi các trẻ đi cùng (children_ages, cách nhau dấu phẩy)</label><input id="children_ages" value="4, 9">
    <div class="chk"><input type="checkbox" id="extra_bed" checked> Giường phụ (extra_bed)</div>
    <div class="chk"><input type="checkbox" id="airport_pickup" checked> Đón sân bay (airport_pickup)</div>
  </div>
  <button onclick="addBooking()">Ghi lượt đặt</button>
  <div id="m_booking"></div>
</div>
<div>
<div class="card"><h2>2. Thêm ngẫu nhiên N lượt đặt</h2>
  <label>N</label><input id="rand_n" type="number" value="100" min="1">
  <button onclick="addRandom()">Thêm ngẫu nhiên</button><div id="m_random"></div></div>
<div class="card"><h2>3. Thêm đoàn tour (bảng sao chép → cả 4 trạm, 2PC)</h2>
  <div class="grid g3"><div><label>Công ty lữ hành</label><input id="agency" value="Vietravel"></div>
  <div><label>Số người</label><input id="size" type="number" value="30"></div>
  <div><label>Ngày khởi hành</label><input id="start_date" type="date" value="2025-07-01"></div></div>
  <button onclick="addGroup()">Thêm đoàn</button><div id="m_group"></div></div>
<div class="card"><h2>4. Thêm phòng vào khách sạn đang chọn ở mục 1</h2>
  <div class="grid g3"><div><label>Loại phòng</label><select id="room_type_code"></select></div>
  <div><label>Tầng</label><input id="floor" type="number" value="9"></div>
  <div><label>Giá/đêm (đồng)</label><input id="rate" type="number" value="1500000"></div></div>
  <button onclick="addRoom()">Thêm phòng</button><div id="m_room"></div></div>
</div></div>
</main>
<script>
const $=id=>document.getElementById(id); let SITES=[], ROOMS=null;
async function api(path, body){ const r = await fetch(path, body? {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)}:{});
  const j = await r.json(); if(!r.ok || j.ok===false) throw new Error(j.error||r.statusText); return j; }
function show(id, ok, text){ $(id).innerHTML = '<div class="msg '+(ok?'ok':'bad')+'"></div>'; $(id).firstChild.textContent = text; }
function loc(j){ return `trạm ${j.site} (${j.region}) · máy ${j.machine} · ${j.ip}:${j.port}`; }
async function init(){
  SITES = await api('/api/sites');
  $('site').innerHTML = SITES.map(s=>`<option value="${s.site}">${s.region} — trạm ${s.site} (máy ${s.machine})</option>`).join('');
  $('site').onchange = loadRooms; $('hotel').onchange = fillRooms; $('guest_type').onchange = showType;
  $('tour_group_id').onchange = groupInfo; await loadRooms(); await loadGroups(); showType();
}
async function loadRooms(){
  const s = $('site').value; const info = SITES.find(x=>x.site==s);
  $('siteinfo').textContent = `ghi vào ${info.ip}:${info.port}, máy ${info.machine}`;
  try { ROOMS = await api('/api/rooms?site='+s); }
  catch(e){ ROOMS = {hotels:[],rooms:[],room_types:[]}; show('m_booking', false, e.message); }
  $('hotel').innerHTML = ROOMS.hotels.map(h=>`<option value="${h[0]}">#${h[0]} ${h[1]} (${h[2]}★)</option>`).join('');
  $('room_type_code').innerHTML = ROOMS.room_types.map(t=>`<option value="${t[0]}">${t[0]} ${t[1]}</option>`).join('');
  fillRooms(); groupInfo();
}
function fillRooms(){ const h = +$('hotel').value;
  $('room').innerHTML = ROOMS.rooms.filter(r=>r[1]==h).map(r=>`<option value="${r[0]}">Phòng ${r[0]} · ${r[3]} (${r[4]} người) · tầng ${r[5]} · ${(+r[6]).toLocaleString('vi-VN')} đ</option>`).join(''); }
async function loadGroups(){ const g = await api('/api/groups');
  $('tour_group_id').innerHTML = g.map(x=>`<option value="${x[0]}">TG${String(x[0]).padStart(4,'0')} · ${x[1]} · ${x[2]} người · ${x[3]}</option>`).join('');
  $('tour_group_id').value = '410'; groupInfo(); }
async function groupInfo(){ if($('guest_type').value!='tour') return; const tg=$('tour_group_id').value; if(!tg) return;
  const r = await api('/api/group_regions?tg='+tg); const s=$('site').value;
  const has = Object.entries(r).filter(([k,v])=>v>0).map(([k,v])=>k+': '+v);
  const cross = Object.entries(r).some(([k,v])=>v>0 && k!=s);
  $('groupinfo').innerHTML = 'Đoàn đang có lượt đặt ở: '+(has.join(', ')||'(chưa có)')+(cross?' → <b class="bad">ghi vào '+s+' sẽ là dòng LIÊN VÙNG</b>':''); }
function showType(){ document.querySelectorAll('.ft').forEach(e=>e.hidden=true); $('f_'+$('guest_type').value).hidden=false; groupInfo(); }
async function addBooking(){
  const b = {site:$('site').value, room_id:$('room').value, guest_name:$('guest_name').value, check_in:$('check_in').value,
    nights:$('nights').value, guest_type:$('guest_type').value, tour_group_id:$('tour_group_id').value, meal_plan:$('meal_plan').value,
    guide_room:$('guide_room').checked, company:$('company').value, tax_code:$('tax_code').value, late_checkout:$('late_checkout').checked,
    children_ages:$('children_ages').value, extra_bed:$('extra_bed').checked, airport_pickup:$('airport_pickup').checked};
  try { const j = await api('/api/booking', b);
    show('m_booking', true, `Đã ghi booking_id ${j.booking_id} vào ${loc(j)} (${j.ms} ms)\\nbooking.request (jsonb) + req_${b.guest_type} trong cùng một giao dịch; bản sao vào CSDL đối chứng bằng 2PC.`+(j.note?'\\n'+j.note:''));
    groupInfo(); } catch(e){ show('m_booking', false, e.message); }
}
async function addRandom(){ try { const j = await api('/api/random', {n:+$('rand_n').value});
    show('m_random', j.ok, `Đã ghi ${j.written}/${j.requested} lượt (${j.ms} ms)\\n`+j.per_site.map(x=>x.ok?`✓ ${loc(x)}: ${x.count} dòng (mã ${x.first_id}…${x.last_id})`:`✗ ${loc(x)}: ${x.error}`).join('\\n'));
  } catch(e){ show('m_random', false, e.message); } }
async function addGroup(){ try { const j = await api('/api/tour_group', {agency:$('agency').value, size:$('size').value, start_date:$('start_date').value});
    show('m_group', true, `Đã thêm đoàn ${j.tour_group_id} (${j.group_code}). ${j.note}`); await loadGroups(); $('tour_group_id').value=j.tour_group_id; }
  catch(e){ show('m_group', false, e.message); } }
async function addRoom(){ try { const j = await api('/api/room', {site:$('site').value, hotel_id:$('hotel').value, room_type_code:$('room_type_code').value, floor:$('floor').value, rate:$('rate').value});
    show('m_room', true, `Đã thêm phòng ${j.room_id} vào ${loc(j)}`); const h=$('hotel').value; await loadRooms(); $('hotel').value=h; fillRooms(); }
  catch(e){ show('m_room', false, e.message); } }
init();
</script></html>"""


if __name__ == "__main__":
    serve(cfg.CFG["app"].get("entry_port", 8080), PAGE,
          {"/api/sites": api_sites, "/api/rooms": api_rooms, "/api/groups": api_groups, "/api/group_regions": api_group_regions},
          {"/api/booking": api_booking, "/api/tour_group": api_tour_group, "/api/room": api_room, "/api/random": api_random},
          title="Giao diện nhập liệu")
