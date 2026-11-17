#!/usr/bin/env python3
"""PHẦN MỞ RỘNG — make ext-bench: so sánh các phương án của E1, E2 (ngoài yêu cầu đề).

  B1 (E1) ghi một lượt đặt vào trạm chính phuquoc với 3 mức synchronous_commit:
        local        = sao chép bất đồng bộ (mặc định của hệ: không chờ bản sao)
        on           = đồng bộ: chờ bản sao ghi WAL xuống đĩa
        remote_apply = đồng bộ: chờ bản sao phát lại xong (đọc ở bản sao thấy ngay)
     Tạm đặt synchronous_standby_names ở trạm chính trong lúc đo; LUÔN trả lại '' khi xong (kể cả lỗi).
  B2 (E1) Q2 ở trạm trung tâm khi srv_phuquoc trỏ tới trạm chính (máy B) và tới bản sao (máy A), trễ 0 và 30 ms.
  B3 (E2) tạo một đoàn tour ở 4 trạm: 4 INSERT autocommit (KHÔNG nguyên tử, chỉ làm mốc) / 2PC không nhật ký /
     2PC có nhật ký fsync (bản E2).
Mỗi phương án đo N lần (bỏ lần đầu), lấy trung vị. Dòng thử được XOÁ khỏi các trạm và ref khi đo xong,
nên dữ liệu và make check không đổi. Kết quả: results/ext/ext_bench.csv
"""
from __future__ import annotations

import csv
import statistics
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))

import delay  # noqa: E402
import ext_replica  # noqa: E402
import twopc  # noqa: E402
from bench import timed_runs  # noqa: E402
from common import RESULTS, SITES_ORDER, SQL_DIR, Config, die  # noqa: E402
from lib import write_booking  # noqa: E402

N = 21                    # bỏ lần đầu -> trung vị của 20
TAG = "EXT bench"         # guest_name / agency của dòng thử, để xoá sau
OUT = RESULTS / "ext" / "ext_bench.csv"


def med(xs):
    xs = xs[1:]
    return round(statistics.median(xs), 2), round(min(xs), 2), round(max(xs), 2)


# ------------------------------------------------------------------ B1
def b1_sync_modes(cfg: Config, site: str, rep: str) -> list[dict]:
    rows = []
    p = cfg.connect(site)
    standby = p.execute("SELECT application_name FROM pg_stat_replication LIMIT 1").fetchone()
    if not standby:
        die("không có bản sao đang stream — chạy make ext-replica trước")
    room = p.execute("SELECT room_id FROM room ORDER BY room_id LIMIT 1").fetchone()[0]
    r = cfg.connect(rep)
    try:
        p.execute(f"ALTER SYSTEM SET synchronous_standby_names = '{standby[0]}'")
        p.execute("SELECT pg_reload_conf()")
        time.sleep(1)
        for mode in ["local", "on", "remote_apply"]:
            p.execute(f"SET synchronous_commit = {mode}")
            w, vis = [], []
            for i in range(N):
                b = {"room_id": room, "guest_name": f"{TAG} {mode} {i}", "check_in": date(2025, 9, 1), "nights": 1,
                     "guest_type": "business",
                     "fields": {"company": "Cty EXT", "tax_code": "0312345678", "late_checkout": False}}
                t0 = time.perf_counter()
                bid = write_booking(p, b)
                t1 = time.perf_counter()
                while not r.execute("SELECT 1 FROM booking WHERE booking_id = %s", [bid]).fetchone():
                    pass
                t2 = time.perf_counter()
                w.append((t1 - t0) * 1000)
                vis.append((t2 - t0) * 1000)
            m, lo, hi = med(w)
            mv, _, _ = med(vis)
            rows.append({"bench": "B1", "variant": f"synchronous_commit={mode}", "delay_ms": 0,
                         "median_ms": m, "min_ms": lo, "max_ms": hi,
                         "note": f"ghi -> thấy ở bản sao (trung vị) {mv} ms"})
            print(f"  B1 {mode:<13} ghi {m:7.2f} ms (min {lo}, max {hi}) · ghi->thấy ở bản sao {mv} ms", flush=True)
    finally:
        p.execute("RESET synchronous_commit")
        p.execute("ALTER SYSTEM RESET synchronous_standby_names")
        p.execute("SELECT pg_reload_conf()")
        print("  (đã trả synchronous_standby_names về mặc định '')")
        p.close()
        r.close()
    return rows


# ------------------------------------------------------------------ B2
def b2_read_target(cfg: Config, site: str, rep: str) -> list[dict]:
    rows = []
    q2 = (SQL_DIR / "queries" / "q2.sql").read_text(encoding="utf-8")
    try:
        for d in [0, cfg.delay_ms]:
            delay.on(cfg) if d else delay.off(cfg, quiet=True)
            for target in [site, rep]:
                ext_replica.point_fdw(cfg, site, target)
                # 2 phiên psql × 5 lần; bỏ lần đầu mỗi phiên (mở kết nối fdw) -> trung vị của 8
                ts = timed_runs(cfg, cfg.central, q2)[1:] + timed_runs(cfg, cfg.central, q2)[1:]
                m, lo, hi = med([0.0] + ts)
                where = f"{target} (máy {cfg.machine_of(target)})"
                rows.append({"bench": "B2", "variant": f"Q2, srv_{site} -> {where}", "delay_ms": d,
                             "median_ms": m, "min_ms": lo, "max_ms": hi,
                             "note": "trễ netem chỉ áp cho trạm xa đã cấu hình; bản sao cùng máy A không bị trễ"
                             if d and target == rep else ""})
                print(f"  B2 trễ {d:>2} ms · srv_{site} -> {where:<28} Q2 {m:8.2f} ms", flush=True)
    finally:
        delay.off(cfg, quiet=True)
        ext_replica.point_fdw(cfg, site, site)
        print(f"  (đã tắt trễ, srv_{site} trỏ lại trạm chính)")
    return rows


# ------------------------------------------------------------------ B3
def plain_insert(cfg: Config, row):
    with cfg.connect(cfg.central) as c:
        new = c.execute("SELECT nextval('tour_group_id_seq')").fetchone()[0]
    row = [new] + row[1:]
    for s in SITES_ORDER:
        with cfg.connect(s, timeout=2) as c:
            c.execute("INSERT INTO tour_group VALUES (%s, %s, %s, %s)", row)


def b3_2pc(cfg: Config) -> list[dict]:
    rows = []
    quiet = lambda *_: None  # noqa: E731
    variants = [
        ("4 INSERT autocommit (không nguyên tử, mốc so sánh)",
         lambda: plain_insert(cfg, [0, TAG, 20, "2025-08-01"])),
        ("2PC không nhật ký (bản cơ bản)",
         lambda: twopc.create_tour_group(cfg, TAG, 20, date(2025, 8, 1), say=quiet, durable=False)),
        ("2PC + nhật ký fsync (E2)",
         lambda: twopc.create_tour_group(cfg, TAG, 20, date(2025, 8, 1), say=quiet, durable=True)),
    ]
    for name, fn in variants:
        ts = []
        for _ in range(N):
            t0 = time.perf_counter()
            fn()
            ts.append((time.perf_counter() - t0) * 1000)
        m, lo, hi = med(ts)
        rows.append({"bench": "B3", "variant": name, "delay_ms": 0, "median_ms": m, "min_ms": lo, "max_ms": hi,
                     "note": "gồm cả mở 4 kết nối (A->2 trạm máy A, 2 trạm máy B)"})
        print(f"  B3 {name:<52} {m:8.2f} ms (min {lo}, max {hi})", flush=True)
    return rows


# ------------------------------------------------------------------ dọn dẹp
def cleanup(cfg: Config, site: str):
    with cfg.connect(site) as c, cfg.connect("ref") as r:
        for conn in (c, r):
            ids = [x[0] for x in conn.execute("SELECT booking_id FROM booking WHERE guest_name LIKE %s",
                                              [TAG + "%"]).fetchall()]
            if ids:
                conn.execute("DELETE FROM req_business WHERE booking_id = ANY(%s)", [ids])
                conn.execute("DELETE FROM booking WHERE booking_id = ANY(%s)", [ids])
    for s in SITES_ORDER + ["ref"]:
        with cfg.connect(s) as c:
            c.execute("DELETE FROM tour_group WHERE agency = %s", [TAG])
    # nhật ký điều phối: bỏ các giao dịch của lần đo (đã xong 'end', không cần cho phục hồi)
    if twopc.LOG.exists():
        import json
        keep = [ln for ln in twopc.LOG.read_text(encoding="utf-8").splitlines()
                if TAG not in ln and not _bench_gid(json.loads(ln)["gid"])]
        twopc.LOG.write_text("\n".join(keep) + ("\n" if keep else ""), encoding="utf-8")
    print("  đã xoá dòng thử khỏi các trạm và ref")


_BENCH_GIDS: set[str] = set()


def _bench_gid(gid: str) -> bool:
    return gid in _BENCH_GIDS


def main():
    cfg = Config()
    site, rep = ext_replica.pick(cfg, None)
    if not ext_replica.try_connect(cfg, rep):
        die("bản sao chưa chạy — make ext-replica")
    with cfg.connect(cfg.central) as c:
        start_tg = c.execute("SELECT last_value FROM tour_group_id_seq").fetchone()[0]
    print(f"make ext-bench · {N} lần mỗi phương án, bỏ lần đầu, trung vị")
    rows = []
    try:
        rows += b1_sync_modes(cfg, site, rep)
        rows += b2_read_target(cfg, site, rep)
        rows += b3_2pc(cfg)
    finally:
        with cfg.connect(cfg.central) as c:
            end_tg = c.execute("SELECT last_value FROM tour_group_id_seq").fetchone()[0]
        _BENCH_GIDS.update(f"tg{i}" for i in range(start_tg + 1, end_tg + 1))
        cleanup(cfg, site)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["bench", "variant", "delay_ms", "median_ms", "min_ms", "max_ms", "note"])
        w.writeheader()
        w.writerows(rows)
    print(f"-> {OUT.relative_to(RESULTS.parent)}")


if __name__ == "__main__":
    main()
