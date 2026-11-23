"""Dashboard (máy A): mỗi trạm một ô; đọc THẲNG từng trạm (không qua postgres_fdw); làm mới mỗi 1 giây."""
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import pandas as pd
import psycopg
import streamlit as st
from lib import ALL_TABLES, REGION_NAME, SITES_ORDER, cfg, connect, log_event, read_events

st.set_page_config(page_title="CS5104 Đề 6 · Dashboard", page_icon="📊", layout="wide")
REPL = {"room_type", "tour_group"}
COUNT_SQL = "SELECT " + ", ".join(f"(SELECT count(*) FROM {t})" for t in ALL_TABLES) + \
            ", (SELECT max(booking_id) FROM booking WHERE booking_id >= 10000000)"


def poll(node: str):
    t0 = time.perf_counter()
    try:
        with connect(node, timeout=1) as c:
            row = c.execute(COUNT_SQL).fetchone()
        return node, {"up": True, "ms": (time.perf_counter() - t0) * 1000,
                      "counts": dict(zip(ALL_TABLES, row[:-1])), "last_new": row[-1]}
    except psycopg.Error as e:
        return node, {"up": False, "err": str(e).strip().splitlines()[0][:90]}


@st.cache_resource
def pool():
    return ThreadPoolExecutor(8)


def snapshot():
    return dict(pool().map(poll, SITES_ORDER + ["ref"]))


def detect(prev, cur):
    """Sinh sự kiện: trạm mất/kết nối lại, dòng mới ở trạm nào."""
    for n, s in cur.items():
        p = prev.get(n)
        if p is None:
            continue
        if p["up"] and not s["up"]:
            log_event("down", n, f"🔴 trạm {n} (máy {cfg.machine_of(n)}) MẤT KẾT NỐI")
        elif not p["up"] and s["up"]:
            log_event("up", n, f"🟢 trạm {n} (máy {cfg.machine_of(n)}) KẾT NỐI LẠI")
        elif p["up"] and s["up"] and n != "ref":
            d = s["counts"]["booking"] - p["counts"]["booking"]
            if d:
                log_event("rows", n, f"➕ {d} lượt đặt mới ở trạm {n} (máy {cfg.machine_of(n)})")


st.title("📊 Dashboard · 4 trạm PostgreSQL trên 2 máy")


@st.fragment(run_every=1)
def live():
    cur = snapshot()
    prev = st.session_state.get("prev", {})
    detect(prev, cur)
    st.session_state["prev"] = cur
    st.caption(f"Cập nhật {datetime.now():%H:%M:%S} · đọc thẳng từng trạm bằng psycopg (không qua postgres_fdw) · "
               f"cấu hình {cfg.path.name}")

    cols = st.columns(4)
    for col, s in zip(cols, SITES_ORDER):
        info = cur[s]
        m = cfg.machine_of(s)
        with col.container(border=True):
            dot = "🟢" if info["up"] else "🔴"
            central = " · ⭐ trung tâm" if s == cfg.central else ""
            st.markdown(f"### {dot} {s}{central}")
            st.markdown(f"**{REGION_NAME[s]}** · máy **{m}**  \n"
                        f"`{cfg.machine_ip(s)}:{cfg.node(s)['port']}`")
            if info["up"]:
                df = pd.DataFrame({"bảng": ALL_TABLES, "số dòng": [info["counts"][t] for t in ALL_TABLES]})
                df["loại"] = ["sao chép" if t in REPL else "mảnh" for t in ALL_TABLES]
                st.dataframe(df, hide_index=True, width="stretch", height=360)
                st.caption(f"phản hồi {info['ms']:.1f} ms · booking_id mới nhất: {info['last_new'] or '—'}")
            else:
                st.error(f"MẤT KẾT NỐI\n\n{info['err']}")

    st.subheader("Tổng hợp so với CSDL đối chứng")
    ref = cur["ref"]
    rows = []
    for t in ALL_TABLES:
        per = [cur[s]["counts"][t] if cur[s]["up"] else None for s in SITES_ORDER]
        if t in REPL:
            total = per[SITES_ORDER.index(cfg.central)]
            rule = "4 bản sao bằng nhau"
            okv = all(p == total for p in per if p is not None)
        else:
            total = sum(p for p in per if p is not None) if None not in per else None
            rule = "Σ mảnh = đối chứng"
            okv = None
        r = ref["counts"][t] if ref["up"] else None
        if okv is None:
            okv = total is not None and total == r
        else:
            okv = okv and total == r
        rows.append({"bảng": t, **{s: p for s, p in zip(SITES_ORDER, per)}, "tổng/bản sao": total,
                     "đối chứng (ref)": r, "quy tắc": rule, "khớp": "✅" if okv else ("⚠️ thiếu trạm" if None in per else "❌")})
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

    st.subheader("Nhật ký sự kiện")
    ev = read_events(25)
    if ev:
        st.dataframe(pd.DataFrame([{"giờ": e["t"], "trạm": e["site"], "sự kiện": e["msg"]} for e in ev]),
                     hide_index=True, width="stretch", height=300)
    else:
        st.caption("(chưa có sự kiện)")


live()
