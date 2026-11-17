#!/usr/bin/env python3
"""make bench — đo Q1–Q5 (N2, N3), tỉ lệ liên vùng (N4) và dung lượng jsonb (N5).

Quy tắc đo (đề, Mục 5): mỗi truy vấn chạy 5 lần, bỏ lần đầu, lấy trung vị 4 lần còn lại.
Thời gian đo NGAY TRONG container của trạm chạy truy vấn (psql qua unix socket, \\timing), nên không
lẫn độ trễ client↔trạm; 5 lần chạy trong cùng một phiên — lần đầu gồm cả chi phí mở kết nối
postgres_fdw tới trạm xa nên bị bỏ.
Đo ở hai trạng thái: không trễ và trễ 30 ms (tools/delay.py), sau đó trả lại trạng thái tắt trễ.

Kết quả:
  results/results.csv            thời gian, số dòng, khớp đối chứng, số trạm chạm
  results/explain/<Q>_<biến thể>_d<trễ>.txt   EXPLAIN (ANALYZE, VERBOSE)
  results/n4_cross.csv, results/n5_storage.csv

    python tools/bench.py                       # đủ Q1–Q5, PROBE, N4, N5 (make bench)
    python tools/bench.py --only Q3 --out results/n4_q3_single_vs_multi.csv
                                                # chỉ các biến thể của Q3 (0 và 30 ms), ghi ra tệp riêng
"""
import csv
import json
import re
import statistics
import sys
from pathlib import Path

import delay
from common import RESULTS, ROOT, SQL_DIR, Config, docker_psql

Q = SQL_DIR / "queries"
RUNS = 5

# (mã, biến thể, trạm chạy, tệp, tệp đối chứng, thay đổi tuỳ chọn server trước khi chạy)
VARIANTS = [
    ("Q1", "site_dalat",          "dalat",   "q1_site.sql",    "q1_ref.sql", {}),
    ("Q1", "central_all_views",   "central", "q1_central.sql", "q1_ref.sql", {}),
    ("Q2", "two_phase",           "central", "q2.sql",         "q2_ref.sql", {}),
    ("Q2", "two_phase_no_async",  "central", "q2.sql",         "q2_ref.sql", {"async_capable": "false"}),
    ("Q2", "two_phase_no_parallel_commit", "central", "q2.sql", "q2_ref.sql", {"parallel_commit": "false"}),
    ("Q2", "base_join",           "central", "q2_base_join.sql", "q2_ref.sql", {}),
    ("Q2", "base_join_remote_est", "central", "q2_base_join.sql", "q2_ref.sql", {"use_remote_estimate": "true"}),
    ("Q2", "naive_all_views",     "central", "q2_naive.sql",   "q2_ref.sql", {}),
    ("Q2", "naive_fetch100",      "central", "q2_naive.sql",   "q2_ref.sql", {"fetch_size": "100"}),
    ("Q3", "pushdown",            "central", "q3.sql",         "q3_ref.sql", {}),
    ("Q3", "pushdown_no_async",   "central", "q3.sql",         "q3_ref.sql", {"async_capable": "false"}),
    ("Q3", "naive_all_views",     "central", "q3_naive.sql",   "q3_ref.sql", {}),
    # N4: đoàn chỉ đi một vùng (đoàn 3, danang) — vẫn phải hỏi cả 4 trạm, nên tốn ngang đoàn 1 (3 vùng)
    ("Q3", "single_region_group", "central", "q3_single.sql",  "q3_single_ref.sql", {}),
    ("Q4", "jsonb_all_views",     "central", "q4.sql",         "q4_ref.sql", {}),
    ("Q5", "relational_view",     "central", "q5.sql",         "q5_ref.sql", {}),
    ("Q5", "base_join",           "central", "q5_base_join.sql", "q5_ref.sql", {}),
]


def set_opts(cfg, opts: dict, restore=False):
    defaults = {"async_capable": "true", "fetch_size": "10000", "parallel_commit": "true", "use_remote_estimate": None}
    if not opts:
        return
    with cfg.connect(cfg.central) as c:
        for s in cfg.remote_sites():
            for k, v in opts.items():
                if defaults[k] is None:       # tuỳ chọn không có sẵn trong server: ADD rồi DROP
                    act = f"DROP {k}" if restore else f"ADD {k} '{v}'"
                else:
                    act = f"SET {k} '{defaults[k] if restore else v}'"
                c.execute(f"ALTER SERVER srv_{s} OPTIONS ({act})")


def timed_runs(cfg, node: str, sql: str) -> list[float]:
    body = sql.strip().rstrip(";") + ";\n"
    script = "\\timing on\n\\o /dev/null\n" + body * RUNS
    out = docker_psql(cfg, node, sql=script)
    times = [float(m) for m in re.findall(r"Time: ([0-9.]+) ms", out)]
    if len(times) != RUNS:
        raise RuntimeError(f"không đọc được thời gian: {out[:300]}")
    return times


def fetch(conn, sql: str):
    return [tuple(map(str, r)) for r in conn.execute(sql).fetchall()]


def plan_sites(conn, sql: str, node: str, cfg) -> tuple[set, int]:
    """Đọc EXPLAIN (VERBOSE, FORMAT JSON): trạm nào bị chạm, bao nhiêu nút Foreign Scan."""
    plan = conn.execute("EXPLAIN (VERBOSE, FORMAT JSON) " + sql.strip().rstrip(";")).fetchone()[0]
    sites, fscans = set(), 0

    def walk(n):
        nonlocal fscans
        if n.get("Node Type") == "Foreign Scan":
            fscans += 1
            text = json.dumps(n.get("Relations", "")) + str(n.get("Schema", ""))
            sites.update(re.findall(r"s_([a-z]+)\.", text + "."))
        elif n.get("Schema") == "public" or "Relation Name" in n and n.get("Schema") == "public":
            sites.add(node)
        for ch in n.get("Plans", []):
            walk(ch)
    walk(plan[0]["Plan"])
    return sites, fscans


def bench_queries(cfg, only: set | None = None) -> list[dict]:
    rows = []
    ref = cfg.connect("ref")
    (RESULTS / "explain").mkdir(parents=True, exist_ok=True)
    expected = {}
    for d in (0, cfg.delay_ms):
        delay.on(cfg) if d else delay.off(cfg)
        for qid, var, where, f, fref, opts in VARIANTS:
            if only and qid not in only:
                continue
            node = cfg.central if where == "central" else where
            sql = (Q / f).read_text(encoding="utf-8")
            set_opts(cfg, opts)
            try:
                times = timed_runs(cfg, node, sql)
                with cfg.connect(node) as c:
                    got = fetch(c, sql)
                    if fref not in expected:
                        expected[fref] = fetch(ref, (Q / fref).read_text(encoding="utf-8"))
                    sites, fscans = plan_sites(c, sql, node, cfg)
                    ex = c.execute("EXPLAIN (ANALYZE, VERBOSE, COSTS OFF) " + sql.strip().rstrip(";")).fetchall()
            finally:
                set_opts(cfg, opts, restore=True)
            (RESULTS / "explain" / f"{qid}_{var}_d{d}.txt").write_text(
                f"-- {qid} · {var} · chạy tại {node} · trễ {d} ms\n" + "\n".join(r[0] for r in ex) + "\n", encoding="utf-8")
            med = statistics.median(times[1:])
            remote = sorted(s for s in sites if s != node)
            extext = "\n".join(r[0] for r in ex)
            plan_ms = re.search(r"Planning Time: ([0-9.]+)", extext)
            exec_ms = re.search(r"Execution Time: ([0-9.]+)", extext)
            r = {"query": qid, "variant": var, "delay_ms": d, "run_at": node,
                 **{f"run{i + 1}_ms": round(t, 3) for i, t in enumerate(times)},
                 "median_ms": round(med, 3), "rows": len(got), "matches_ref": got == expected[fref],
                 "sites_touched": len(sites | {node}), "remote_sites": " ".join(remote) or "-",
                 "foreign_scans": fscans, "async_scans": extext.count("Async Foreign Scan"),
                 "explain_planning_ms": float(plan_ms.group(1)) if plan_ms else None,
                 "explain_execution_ms": float(exec_ms.group(1)) if exec_ms else None}
            rows.append(r)
            print(f"  {qid} {var:<22} trễ {d:>2} ms  trung vị {med:>9.2f} ms  {len(got):>5} dòng  "
                  f"đúng={'✓' if r['matches_ref'] else '✗'}  trạm xa: {r['remote_sites']}", flush=True)
    delay.off(cfg)
    ref.close()
    return rows


def probe_rtt(cfg) -> list[dict]:
    """Chi phí một truy vấn tối thiểu qua postgres_fdw tới từng trạm xa (≈ 5 vòng khứ hồi, Hình 1.2)."""
    out = []
    for d in (0, cfg.delay_ms):
        delay.on(cfg) if d else delay.off(cfg)
        for s in cfg.remote_sites():
            sql = f"SELECT capacity FROM s_{s}.room_type WHERE room_type_code = 'RT01'"
            times = timed_runs(cfg, cfg.central, sql)
            med = statistics.median(times[1:])
            out.append({"query": "PROBE", "variant": f"probe_{s}_machine{cfg.machine_of(s)}", "delay_ms": d,
                        "run_at": cfg.central, **{f"run{i + 1}_ms": round(t, 3) for i, t in enumerate(times)},
                        "median_ms": round(med, 3), "rows": 1, "matches_ref": True, "sites_touched": 2,
                        "remote_sites": s, "foreign_scans": 1, "async_scans": 0,
                        "explain_planning_ms": None, "explain_execution_ms": None})
            print(f"  PROBE {s:<9} (máy {cfg.machine_of(s)}) trễ {d:>2} ms  trung vị {med:8.2f} ms", flush=True)
    delay.off(cfg)
    return out


def n4(cfg):
    with cfg.connect(cfg.central) as c:
        r = c.execute("""
            WITH b AS (SELECT b.booking_id, b.tour_group_id, h.region
                       FROM all_booking b JOIN all_room r USING (room_id) JOIN all_hotel h USING (hotel_id)
                       WHERE b.tour_group_id IS NOT NULL),
                 g AS (SELECT tour_group_id, count(DISTINCT region) nreg FROM b GROUP BY 1)
            SELECT (SELECT count(*) FROM all_booking),
                   (SELECT count(*) FROM b),
                   (SELECT count(*) FROM b JOIN g USING (tour_group_id) WHERE nreg >= 2),
                   (SELECT count(*) FROM g WHERE nreg >= 2),
                   (SELECT count(*) FROM g)""").fetchone()
        g1 = c.execute("""SELECT h.region, count(*) FROM all_booking b JOIN all_room r USING (room_id)
                          JOIN all_hotel h USING (hotel_id) WHERE b.tour_group_id = 1 GROUP BY 1 ORDER BY 1""").fetchall()
    total, tour, cross, mgroups, groups = r
    with open(RESULTS / "n4_cross.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["metric", "value"])
        w.writerows([("bookings_total", total), ("tour_bookings", tour), ("cross_region_bookings", cross),
                     ("cross_region_rate", round(cross / total, 4)), ("multi_region_groups", mgroups),
                     ("tour_groups_with_bookings", groups)] +
                    [(f"Q3_group1_rows_{reg}", n) for reg, n in g1])
    print(f"  N4: {cross}/{total} lượt đặt liên vùng = {cross / total:.2%}; {mgroups} đoàn đi ≥ 2 vùng; "
          f"đoàn 1: {dict(g1)}")


def n5(cfg):
    out = {}
    q = lambda s: docker_psql(cfg, "ref", sql=s, args=["-At"]).strip()
    out["booking_rows"] = q("SELECT count(*) FROM booking")
    out["jsonb_request_bytes"] = q("SELECT sum(pg_column_size(request)) FROM booking")
    for t in ("tour", "business", "family"):
        out[f"jsonb_bytes_{t}"] = q(f"SELECT sum(pg_column_size(request)) FROM booking WHERE guest_type = '{t}'")
        out[f"jsonb_avg_bytes_{t}"] = q(f"SELECT round(avg(pg_column_size(request)), 1) FROM booking WHERE guest_type = '{t}'")
    rel = "('req_tour'),('req_business'),('req_family'),('req_family_child')"
    out["relational_heap_bytes"] = q(f"SELECT sum(pg_relation_size(t::regclass)) FROM (VALUES {rel}) v(t)")
    out["relational_total_bytes_with_pk"] = q(f"SELECT sum(pg_total_relation_size(t::regclass)) FROM (VALUES {rel}) v(t)")
    out["relational_rows"] = q("SELECT (SELECT count(*) FROM req_tour)+(SELECT count(*) FROM req_business)"
                               "+(SELECT count(*) FROM req_family)+(SELECT count(*) FROM req_family_child)")
    out["booking_heap_bytes"] = q("SELECT pg_relation_size('booking')")
    q4 = (Q / "q4_ref.sql").read_text(encoding="utf-8")
    q5 = (Q / "q5_ref.sql").read_text(encoding="utf-8")
    out["q4_ref_no_gin_ms"] = round(statistics.median(timed_runs(cfg, "ref", q4)[1:]), 3)
    out["q5_ref_ms"] = round(statistics.median(timed_runs(cfg, "ref", q5)[1:]), 3)
    for opclass in ("jsonb_path_ops", "jsonb_ops"):
        q(f"DROP INDEX IF EXISTS booking_request_gin; CREATE INDEX booking_request_gin ON booking USING gin (request {opclass}); ANALYZE booking")
        out[f"gin_{opclass}_bytes"] = q("SELECT pg_relation_size('booking_request_gin')")
        out[f"q4_ref_gin_{opclass}_ms"] = round(statistics.median(timed_runs(cfg, "ref", q4)[1:]), 3)
        ex = q("EXPLAIN (ANALYZE, COSTS OFF) " + q4.strip().rstrip(";"))
        (RESULTS / "explain" / f"Q4_ref_gin_{opclass}.txt").write_text(ex + "\n", encoding="utf-8")
    q("DROP INDEX IF EXISTS booking_request_gin")
    (RESULTS / "explain" / "Q4_ref_no_gin.txt").write_text(q("EXPLAIN (ANALYZE, COSTS OFF) " + q4.strip().rstrip(";")) + "\n", encoding="utf-8")
    with open(RESULTS / "n5_storage.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["metric", "value"])
        w.writerows(out.items())
    print("  N5: " + ", ".join(f"{k}={v}" for k, v in out.items()))


def main():
    cfg = Config()
    RESULTS.mkdir(exist_ok=True)
    args = sys.argv[1:]
    if "--only" in args:          # đo riêng vài truy vấn, không ghi đè results.csv
        only = {q.upper() for q in args[args.index("--only") + 1].split(",")}
        out = Path(args[args.index("--out") + 1]) if "--out" in args else RESULTS / f"bench_{'_'.join(sorted(only))}.csv"
        rows = bench_queries(cfg, only)
        with open(out, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        print(f"-> {out}")
        sys.exit(0 if all(r["matches_ref"] for r in rows) else 1)
    print("N2/N3 · Q1–Q5 (5 lần, bỏ lần đầu, trung vị)")
    rows = bench_queries(cfg)
    print("N3 · chi phí một lượt hỏi tối thiểu tới từng trạm xa")
    rows += probe_rtt(cfg)
    with open(RESULTS / "results.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print("-> results/results.csv, results/explain/")
    print("N4 · dòng liên vùng")
    n4(cfg)
    print("N5 · dung lượng jsonb so với bản quan hệ, có/không GIN (trên CSDL đối chứng)")
    n5(cfg)
    bad = [r for r in rows if not r["matches_ref"]]
    if bad:
        print("CÓ KẾT QUẢ KHÁC ĐỐI CHỨNG:", [(r["query"], r["variant"]) for r in bad])
        sys.exit(1)


if __name__ == "__main__":
    main()
