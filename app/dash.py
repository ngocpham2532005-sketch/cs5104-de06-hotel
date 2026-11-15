"""
Dashboard theo dõi (máy A) — `make dash`, mở http://<máy A>:8081

- Mỗi trạm một ô: máy, IP:cổng, trạng thái kết nối (xanh/đỏ), số dòng từng bảng.
  Đọc THẲNG từng trạm (mỗi trạm một luồng, kết nối riêng), KHÔNG qua postgres_fdw.
- Bảng tổng hợp: tổng các mảnh (bảng chia) / giá trị sao chép so với CSDL đối chứng.
- Nhật ký sự kiện: dòng mới ở trạm nào, trạm mất kết nối / kết nối lại.
- Luồng nền đọc mỗi 1 s; trang tự làm mới mỗi 1 s (≤ 2 s theo yêu cầu).
"""
import datetime as dt, threading, time
from web import CSS, serve
import cfg
from cfg import ALL_TABLES, FRAGMENTED, REGION_VN, SITES, connect, connect_ref, site

POLL = 1.0
COUNT_SQL = "SELECT " + ", ".join(f"(SELECT count(*) FROM {t})" for t in ALL_TABLES)
lock = threading.Lock()
STATE = {s: {"up": None, "counts": {}, "ms": None, "since": None, "error": ""} for s in SITES + ["ref"]}
EVENTS = []


def log(kind, text):
    with lock:
        EVENTS.insert(0, {"t": dt.datetime.now().strftime("%H:%M:%S"), "kind": kind, "text": text})
        del EVENTS[200:]


def watcher(s):
    conn = None
    label = "CSDL đối chứng" if s == "ref" else f"trạm {s}"
    while True:
        t0 = time.perf_counter()
        try:
            if conn is None:
                conn = (connect_ref if s == "ref" else lambda **k: connect(s, **k))(connect_timeout=1, timeout=3, app="dashboard")
            _, rows = conn.query(COUNT_SQL)
            counts = dict(zip(ALL_TABLES, rows[0]))
            ms = (time.perf_counter() - t0) * 1000
            with lock:
                st = STATE[s]; prev_up, prev = st["up"], st["counts"]
                st.update(up=True, counts=counts, ms=round(ms, 1), error="")
                if prev_up is not True:
                    st["since"] = time.time()
            if prev_up is False:
                log("up", f"{label} KẾT NỐI LẠI")
            elif prev_up is None:
                log("up", f"{label} kết nối OK")
            if prev and s != "ref":
                diff = {t: counts[t] - prev.get(t, 0) for t in ALL_TABLES if counts[t] != prev.get(t, 0)}
                if diff:
                    log("data", f"{label}: " + ", ".join(f"{t} {d:+d}" for t, d in diff.items()))
        except Exception as e:  # noqa: BLE001
            if conn:
                conn.close()
            conn = None
            with lock:
                st = STATE[s]; prev_up = st["up"]
                st.update(up=False, ms=None, error=str(e)[:160])
                if prev_up is not False:
                    st["since"] = time.time()
            if prev_up is not False:
                log("down", f"{label} MẤT KẾT NỐI ({str(e)[:80]})")
        time.sleep(max(0.0, POLL - (time.perf_counter() - t0)))


def api_state(_):
    with lock:
        sites = []
        for s in SITES:
            i = site(s); st = STATE[s]
            sites.append({"site": s, "region": REGION_VN[s], "machine": i["machine"], "ip": i["ip"], "port": i["port"],
                          "central": i["central"], **st})
        ref = dict(STATE["ref"])
        events = list(EVENTS[:60])
    totals = []
    for t in ALL_TABLES:
        up = [x for x in sites if x["up"] and x["counts"]]
        if t in FRAGMENTED:
            val = sum(x["counts"][t] for x in up); kind = "chia"
        else:
            vals = {x["counts"][t] for x in up}
            val = next(iter(vals)) if len(vals) == 1 else None; kind = "sao chép" + ("" if len(vals) <= 1 else " — LỆCH giữa các trạm!")
        missing = [x["site"] for x in sites if not x["up"]]
        r = ref["counts"].get(t) if ref["up"] else None
        totals.append({"table": t, "kind": kind, "value": val, "ref": r, "missing": missing,
                       "match": (val == r and not missing) if r is not None and val is not None else None})
    return {"sites": sites, "ref": ref, "totals": totals, "events": events, "now": dt.datetime.now().strftime("%H:%M:%S")}


PAGE = """<!doctype html><html lang="vi"><meta charset="utf-8"><title>Dashboard — Đề 6 Khách sạn</title>
<style>""" + CSS + """
.site{border-top:6px solid #9aa0a6}.site.up{border-top-color:#1e8e3e}.site.down{border-top-color:#d93025;background:#fff7f6}
.dot{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px;background:#9aa0a6}.up .dot{background:#1e8e3e}.down .dot{background:#d93025}
.big{font-size:22px;font-weight:600}.ev{font-size:12.5px;font-family:ui-monospace,Menlo,Consolas,monospace;max-height:340px;overflow:auto}
.ev div{padding:2px 0;border-bottom:1px dashed #eee}.ev .down{color:#c5221f}.ev .up{color:#137333}.ev .data{color:#1a4fbf}
td.flash{background:#fff3c4;transition:background 1.5s}
</style>
<header><h1>Dashboard · Chuỗi khách sạn nghỉ dưỡng — 4 trạm</h1><span>đọc thẳng từng trạm, không qua postgres_fdw · làm mới mỗi 1 s · <b id="now"></b></span></header>
<main><div id="sites" class="grid g4"></div>
<div class="grid g2"><div class="card"><h2>Tổng hợp so với CSDL đối chứng (hotel_ref)</h2><div id="totals"></div></div>
<div class="card"><h2>Nhật ký sự kiện</h2><div id="events" class="ev"></div></div></div></main>
<script>
const TABLES = %TABLES%; let PREV = {};
const fmt = n => n==null ? '—' : Number(n).toLocaleString('vi-VN');
async function tick(){
  let j; try { j = await (await fetch('/api/state')).json(); } catch(e){ document.getElementById('now').textContent='mất kết nối tới dashboard'; return; }
  document.getElementById('now').textContent = j.now;
  document.getElementById('sites').innerHTML = j.sites.map(s => {
    const cls = s.up===true?'up':(s.up===false?'down':'');
    const rows = TABLES.map(t => { const v=s.counts[t]; const k=s.site+t; const fl = PREV[k]!=null && v!=null && PREV[k]!==v; PREV[k]=v;
      return `<tr><td>${t}</td><td class="n ${fl?'flash':''}">${fmt(v)}</td></tr>`; }).join('');
    return `<div class="card site ${cls}"><div><span class="dot"></span><b>${s.region}</b> · trạm ${s.site}${s.central?' (trung tâm)':''}</div>
      <div class="muted">máy ${s.machine} · ${s.ip}:${s.port} · ${s.up?('đọc '+s.ms+' ms'):(s.up===false?'<b class="bad">MẤT KẾT NỐI</b>':'đang kết nối…')}</div>
      <div class="big">${fmt(s.counts.booking)} <span class="muted">booking</span></div>
      <table>${rows}</table>${s.error?'<div class="muted bad">'+s.error+'</div>':''}</div>`; }).join('');
  document.getElementById('totals').innerHTML = '<table><tr><th>bảng</th><th>loại</th><th class="n">hệ phân tán</th><th class="n">đối chứng</th><th>khớp</th></tr>' +
    j.totals.map(t => `<tr><td>${t.table}</td><td class="muted">${t.kind}</td><td class="n">${fmt(t.value)}</td><td class="n">${fmt(t.ref)}</td>
      <td>${t.match===true?'<span class="ok">✓</span>':(t.missing.length?'<span class="bad">thiếu '+t.missing.join(',')+'</span>':(t.match===false?'<span class="bad">✗</span>':'—'))}</td></tr>`).join('') + '</table>' +
    `<div class="muted">CSDL đối chứng: ${j.ref.up?'kết nối OK':'<b class="bad">mất kết nối</b>'} · bảng chia = tổng các mảnh; bảng sao chép = giá trị chung của các trạm</div>`;
  document.getElementById('events').innerHTML = j.events.map(e => `<div class="${e.kind}">${e.t}  ${e.text}</div>`).join('');
}
tick(); setInterval(tick, 1000);
</script></html>"""


if __name__ == "__main__":
    for s in SITES + ["ref"]:
        threading.Thread(target=watcher, args=(s,), daemon=True).start()
    import json
    serve(cfg.CFG["app"].get("dash_port", 8081), PAGE.replace("%TABLES%", json.dumps(ALL_TABLES)),
          {"/api/state": api_state}, title="Dashboard")
