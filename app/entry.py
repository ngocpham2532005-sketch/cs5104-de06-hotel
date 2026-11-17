"""Giao diện nhập liệu (máy A) — ghi THẲNG vào đúng trạm theo thiết kế phân tán.

- Lượt đặt phòng (đối tượng chính, có cột jsonb) + dòng phụ thuộc req_* (bản quan hệ): một giao dịch, một trạm.
- Trạm đích = vùng của khách sạn được chọn. Trạm mất kết nối -> báo lỗi, KHÔNG ghi sang trạm khác.
- Đoàn tour mới: ghi bản sao vào cả 4 trạm bằng cam kết hai pha (PREPARE TRANSACTION);
  bộ điều phối ghi nhật ký quyết định bền vững và phục hồi được (mở rộng E2, tools/twopc.py).
- Mọi dòng ghi thành công được chép thêm vào CSDL đối chứng (để Q1–Q5 tiếp tục so sánh được).
"""
import random
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import psycopg
import streamlit as st
from lib import (REGION_NAME, SITES_ORDER, WEIGHTS, build_request, cfg, connect, group_code, log_event,
                 site_label, write_booking)

import twopc  # noqa: E402  (tools/ đã có trong sys.path qua lib)

st.set_page_config(page_title="CS5104 Đề 6 · Nhập liệu", page_icon="🏨", layout="wide")
st.title("🏨 Nhập liệu · Chuỗi khách sạn nghỉ dưỡng (4 trạm)")
st.caption("Ghi thẳng vào trạm của vùng khách sạn. Booking + jsonb + bản quan hệ trong một giao dịch.")


# ------------------------------------------------------------------ đọc danh mục từ đúng trạm
@st.cache_data(ttl=20, show_spinner=False)
def hotels(site):
    with connect(site) as c:
        return c.execute("SELECT hotel_id, name, stars FROM hotel ORDER BY hotel_id").fetchall()


@st.cache_data(ttl=20, show_spinner=False)
def rooms(site, hotel_id):
    with connect(site) as c:
        return c.execute("SELECT r.room_id, r.room_type_code, t.name, r.floor, r.rate FROM room r "
                         "JOIN room_type t USING (room_type_code) WHERE hotel_id = %s ORDER BY room_id",
                         [hotel_id]).fetchall()


@st.cache_data(ttl=20, show_spinner=False)
def room_ids(site):
    with connect(site) as c:
        return [r[0] for r in c.execute("SELECT room_id FROM room").fetchall()]


@st.cache_data(ttl=20, show_spinner=False)
def tour_groups(site):
    with connect(site) as c:
        return c.execute("SELECT tour_group_id, agency, size, start_date FROM tour_group ORDER BY tour_group_id").fetchall()


def group_regions(tg: int):
    """Đoàn đã có phòng ở những vùng nào — hỏi thẳng từng trạm, song song."""
    def one(s):
        try:
            with connect(s, timeout=1) as c:
                return s, c.execute("SELECT count(*) FROM booking WHERE tour_group_id = %s", [tg]).fetchone()[0]
        except psycopg.Error:
            return s, None
    with ThreadPoolExecutor(4) as ex:
        return dict(ex.map(one, SITES_ORDER))


def mirror_ref(rows):
    """Chép các lượt đặt vừa ghi thành công vào CSDL đối chứng (giữ nguyên booking_id)."""
    try:
        with connect("ref") as c:
            for bid, b in rows:
                write_booking(c, b, booking_id=bid)
    except psycopg.Error as e:
        st.warning(f"Đã ghi vào trạm nhưng chưa chép được sang CSDL đối chứng: {e}")


def save(site, b) -> int | None:
    try:
        with connect(site) as c:
            bid = write_booking(c, b)
    except psycopg.OperationalError as e:
        st.error(f"❌ KHÔNG GHI ĐƯỢC — {site_label(site)} mất kết nối. Dữ liệu KHÔNG được ghi sang trạm khác.\n\n`{str(e).strip()[:200]}`")
        log_event("error", site, f"nhập liệu thất bại: trạm {site} mất kết nối")
        return None
    except psycopg.Error as e:
        st.error(f"❌ Trạm {site} từ chối dòng (ràng buộc): `{str(e).strip()[:300]}`")
        return None
    mirror_ref([(bid, b)])
    return bid


tab1, tab2, tab3 = st.tabs(["➕ Thêm lượt đặt", "🎲 Thêm ngẫu nhiên N dòng", "👥 Thêm đoàn tour (2PC)"])

# ------------------------------------------------------------------ 1. thêm một lượt đặt
with tab1:
    c1, c2, c3 = st.columns(3)
    site = c1.selectbox("Vùng (quyết định trạm đích)", SITES_ORDER, format_func=lambda s: f"{REGION_NAME[s]} ({s})")
    st.markdown("Sẽ ghi vào " + site_label(site))
    try:
        hs = hotels(site)
        hotel = c2.selectbox("Khách sạn", hs, format_func=lambda h: f"#{h[0]} {h[1]} ({h[2]}★)")
        rs = rooms(site, hotel[0])
        room = c3.selectbox("Phòng", rs, format_func=lambda r: f"#{r[0]} · {r[2]} · tầng {r[3]} · {int(r[4]):,}đ/đêm")
        tgs = tour_groups(site)
        online = True
    except psycopg.Error as e:
        st.error(f"❌ {site_label(site)} đang mất kết nối — không đọc được danh mục và sẽ không ghi được. (`{str(e).strip()[:120]}`)")
        online, room, tgs = False, None, []

    d1, d2, d3, d4 = st.columns(4)
    guest_name = d1.text_input("Tên khách", "Nguyễn Văn Demo")
    check_in = d2.date_input("Ngày nhận phòng", date(2025, 7, 15))
    nights = d3.number_input("Số đêm", 1, 30, 2)
    guest_type = d4.radio("Loại khách (dạng jsonb)", ["tour", "business", "family"], horizontal=True)

    fields, tg = {}, None
    if guest_type == "tour":
        e1, e2, e3 = st.columns(3)
        tgrow = e1.selectbox("Đoàn tour", tgs, format_func=lambda g: f"{group_code(g[0])} · {g[1]} · {g[2]} khách",
                             index=0 if tgs else None)
        tg = tgrow[0] if tgrow else None
        fields["meal_plan"] = e2.selectbox("Gói ăn (meal_plan)", ["BB", "HB", "FB"])
        fields["guide_room"] = e3.checkbox("Phòng cho hướng dẫn viên (guide_room)")
        if tg:
            reg = group_regions(tg)
            have = [s for s, n in reg.items() if n]
            down = [s for s, n in reg.items() if n is None]
            txt = ", ".join(f"{s} ({reg[s]})" for s in have) or "chưa có"
            cross = bool(have) and (set(have) | {site}) != {site}
            st.info(f"Đoàn {group_code(tg)} đã có phòng ở: {txt}" + (f" · không hỏi được: {', '.join(down)}" if down else "")
                    + ("\n\n🔀 **Dòng LIÊN VÙNG**: đoàn này có phòng ở vùng khác — Q3 sẽ phải đi qua mạng để thấy dòng này."
                       if cross else ""))
    elif guest_type == "business":
        e1, e2, e3 = st.columns(3)
        fields["company"] = e1.text_input("Công ty", "Cty TNHH Demo")
        fields["tax_code"] = e2.text_input("Mã số thuế", "0312345678")
        fields["late_checkout"] = e3.checkbox("Trả phòng muộn (late_checkout)")
    else:
        e1, e2, e3 = st.columns(3)
        fields["extra_bed"] = e1.checkbox("Giường phụ (extra_bed)")
        fields["airport_pickup"] = e2.checkbox("Đón sân bay (airport_pickup)", True)
        ages = e3.text_input("Tuổi các trẻ (children_ages, cách nhau dấu phẩy)", "4, 9")
        fields["children_ages"] = [int(x) for x in ages.replace(" ", "").split(",") if x != ""]

    b = {"room_id": room[0] if room else None, "guest_name": guest_name, "check_in": check_in, "nights": int(nights),
         "guest_type": guest_type, "tour_group_id": tg, "fields": fields}
    req, rel = build_request(guest_type, fields, tg) if (guest_type != "tour" or tg) else ({}, [])
    with st.expander("Xem trước jsonb và bản quan hệ sẽ ghi"):
        st.json(req)
        st.write([f"{t}({', '.join(c)}) = {v}" for t, c, v in rel])
    if st.button("💾 Ghi lượt đặt", type="primary", disabled=room is None and online):
        bid = save(site, b)
        if bid:
            st.success(f"✅ Đã ghi booking_id = **{bid}** (+ {len(rel)} dòng bản quan hệ) vào {site_label(site)}")
            log_event("insert", site, f"booking {bid} ({guest_type}) ghi vào {site} / máy {cfg.machine_of(site)}")

# ------------------------------------------------------------------ 2. ngẫu nhiên N dòng
with tab2:
    n = st.number_input("Số dòng N", 1, 5000, 100, step=10)
    only = st.multiselect("Chỉ ghi vào các trạm (để trống = theo tỉ lệ vùng của đề)", SITES_ORDER)
    if st.button("🎲 Thêm ngẫu nhiên N dòng", type="primary"):
        rnd = random.Random()
        sites = only or SITES_ORDER
        weights = [WEIGHTS[s] for s in sites]
        plan = {}
        for _ in range(int(n)):
            plan.setdefault(rnd.choices(sites, weights)[0], []).append(None)
        result, mirrored = {}, []
        prog = st.progress(0.0)
        done = 0
        for s, items in plan.items():
            try:
                rids, groups = room_ids(s), [g[0] for g in tour_groups(s)]
                with connect(s) as c:
                    for _ in items:
                        t = rnd.choices(["tour", "business", "family"], [0.45, 0.35, 0.20])[0]
                        tgid = rnd.choice(groups) if t == "tour" else None
                        f = ({"meal_plan": rnd.choice(["BB", "HB", "FB"]), "guide_room": rnd.random() < 0.1} if t == "tour" else
                             {"company": "Cty TNHH Ngẫu Nhiên", "tax_code": f"03{rnd.randint(10**7, 10**8 - 1)}",
                              "late_checkout": rnd.random() < 0.3} if t == "business" else
                             {"extra_bed": rnd.random() < 0.4, "airport_pickup": rnd.random() < 0.5,
                              "children_ages": [rnd.randint(0, 15) for _ in range(rnd.randint(0, 3))]})
                        b = {"room_id": rnd.choice(rids), "guest_name": f"Khách ngẫu nhiên {rnd.randint(1, 9999)}",
                             "check_in": date(2025, rnd.randint(1, 12), rnd.randint(1, 28)), "nights": rnd.randint(1, 7),
                             "guest_type": t, "tour_group_id": tgid, "fields": f}
                        mirrored.append((write_booking(c, b), b))
                        done += 1
                        prog.progress(done / n)
                result[s] = f"✅ {len(items)} dòng"
                log_event("insert", s, f"{len(items)} dòng ngẫu nhiên ghi vào {s} / máy {cfg.machine_of(s)}")
            except psycopg.OperationalError:
                result[s] = f"❌ mất kết nối — {len(items)} dòng KHÔNG ghi (không chuyển sang trạm khác)"
                log_event("error", s, f"thêm ngẫu nhiên: trạm {s} mất kết nối")
        mirror_ref(mirrored)
        for s, r in result.items():
            st.write(f"- {site_label(s)}: {r}")

# ------------------------------------------------------------------ 3. đoàn tour mới (bảng sao chép, 2PC)
with tab3:
    st.markdown("`tour_group` được **sao chép ra cả 4 trạm**, nên đoàn mới phải ghi vào 4 bản sao một cách nguyên tử: "
                "cam kết hai pha (Chương 4) — mọi trạm `PREPARE TRANSACTION` xong mới `COMMIT PREPARED`. "
                "Một trạm mất kết nối ⇒ huỷ toàn bộ.")
    a1, a2, a3 = st.columns(3)
    agency = a1.selectbox("Công ty lữ hành", ["Saigontourist", "Vietravel", "BenThanh Tourist", "Hanoitourist", "TST Tourist"])
    size = a2.number_input("Số khách", 10, 45, 20)
    start = a3.date_input("Ngày khởi hành", date(2025, 8, 1))
    if st.button("👥 Tạo đoàn (2PC trên 4 trạm)", type="primary"):
        # E2 (mở rộng): 2PC có nhật ký điều phối bền vững — tools/twopc.py, xem docs/NANG_CAO.md
        log = []
        try:
            new_id, pending = twopc.create_tour_group(cfg, agency, size, start, say=log.append)
            st.cache_data.clear()
            if pending:
                st.warning(f"⚠ Đoàn {group_code(new_id)} ĐÃ được quyết định commit nhưng {pending} chưa nhận "
                           "COMMIT PREPARED — chạy `make ext-2pc-recover` khi trạm sống lại.")
            else:
                st.success(f"✅ Đã tạo đoàn {group_code(new_id)} (tour_group_id = {new_id}) ở cả 4 trạm")
            log_event("insert", "all", f"đoàn {group_code(new_id)} ghi vào 4 trạm bằng 2PC")
        except twopc.TwoPCError as e:
            st.error(f"❌ {e}")
        st.code("\n".join(log) or "(không có bước nào)")
    with st.expander("🛠 Giao dịch lưỡng lự (mở rộng E2)"):
        found = twopc.in_doubt(cfg)
        n = sum(len(v or []) for v in found.values())
        st.write({s: ("mất kết nối" if v is None else [x.gtrid for x, _ in v]) for s, v in found.items()})
        if st.button(f"Phục hồi theo nhật ký điều phối ({n} giao dịch)", disabled=n == 0):
            out = []
            twopc.recover(cfg, say=out.append)
            st.cache_data.clear()
            st.code("\n".join(out))
