"""
make bench — đo Q1–Q5 và tính các con số N1–N5.

- Mỗi truy vấn chạy 5 lần trên cùng một kết nối, bỏ lần đầu (khởi động, mở kết nối postgres_fdw),
  lấy trung vị 4 lần còn lại. Thời gian đo ở phía client (gồm cả nhận kết quả).
- So kết quả với CSDL đối chứng (phải giống hệt từng dòng).
- Lưu EXPLAIN (ANALYZE, VERBOSE) của Q1–Q5; đếm Foreign Scan và số trạm mỗi truy vấn chạm (N2).
- Ghi results/results.csv (nối thêm), results/n1.csv, n4.csv, n5.csv, results/explain/delay<ms>/*.txt
- Nhãn trễ đọc từ results/.delay (do `make delay-on/off` ghi).
"""
import csv, datetime as dt, json, os, re, statistics, sys, time
from cfg import (CENTRAL, RESULTS, ROOT, SITES, SITE_DIR, DATA_DIR, ALL_TABLES, connect, connect_ref, site)

QDIR = ROOT / "sql" / "queries"
RUNS = int(os.environ.get("RUNS", 5))
TG = int(os.environ.get("TG", 410))


def load_sql(name, tg=TG):
    txt = (QDIR / name).read_text(encoding="utf-8")
    return re.sub(r"(?<!:):tg\b", str(tg), txt)


def timed(conn, sql):
    times, rows = [], None
    for _ in range(RUNS):
        t0 = time.perf_counter()
        _, rows = conn.query(sql)
        times.append((time.perf_counter() - t0) * 1000)
    return times, rows


def sites_touched(plan, where):
    """N2: số nút Foreign Scan và tập trạm truy vấn chạm (trạm xa qua s_<trạm>, trạm chạy nếu quét bảng cục bộ)."""
    lines = plan.splitlines()
    nfs = sum("Foreign Scan" in ln for ln in lines)
    fs = "\n".join(ln for ln in lines if "Foreign Scan" in ln or "Relations:" in ln)
    touched = set(re.findall(r"s_(dalat|nhatrang|phuquoc|danang)\.", fs))
    if any("Scan" in ln and re.search(r" on public\.\w+", ln) for ln in lines):
        touched.add(where)
    return nfs, sorted(touched, key=SITES.index)


def pick_single_group(ref):
    return ref.scalar("""SELECT b.tour_group_id FROM booking b JOIN room r USING (room_id) JOIN hotel h USING (hotel_id)
                         WHERE b.tour_group_id IS NOT NULL GROUP BY 1 HAVING count(DISTINCT h.region) = 1
                         ORDER BY count(*) DESC, 1 LIMIT 1""")


def main():
    RESULTS.mkdir(exist_ok=True)
    label = (RESULTS / ".delay").read_text().strip() if (RESULTS / ".delay").exists() else "0"
    exdir = RESULTS / "explain" / f"delay{label}"; exdir.mkdir(parents=True, exist_ok=True)
    ref = connect_ref(); central = connect(CENTRAL); dalat = connect("dalat")
    single = pick_single_group(ref)
    plan_list = [
        ("Q1", "dalat", dalat, "q1_site.sql", "ref/q1.sql", TG),
        ("Q1@central", CENTRAL, central, "q1.sql", "ref/q1.sql", TG),
        ("Q2", CENTRAL, central, "q2.sql", "ref/q2.sql", TG),
        ("Q2-global", CENTRAL, central, "q2_global.sql", "ref/q2.sql", TG),
        ("Q3", CENTRAL, central, "q3.sql", "ref/q3.sql", TG),
        ("Q3-global", CENTRAL, central, "q3_global.sql", "ref/q3.sql", TG),
        (f"Q3-single(tg={single})", CENTRAL, central, "q3.sql", "ref/q3.sql", single),
        ("Q4", CENTRAL, central, "q4.sql", "ref/q4.sql", TG),
        ("Q5", CENTRAL, central, "q5.sql", "ref/q5.sql", TG),
    ]
    now = dt.datetime.now().isoformat(timespec="seconds")
    out_rows = []
    print(f"Bench · trễ {label} ms · {RUNS} lần/truy vấn, bỏ lần đầu, lấy trung vị · Q3 tg={TG}")
    print(f"{'truy vấn':<22}{'trạm chạy':<10}{'trung vị ms':>12}{'dòng':>7}{'đúng':>6}{'FScan':>7}  trạm chạm")
    for qid, where, conn, f, rf, tg in plan_list:
        sql = load_sql(f, tg)
        _, ref_rows = ref.query(load_sql(rf, tg))
        times, rows = timed(conn, sql)
        med = statistics.median(times[1:])
        plan = "\n".join(r[0] for r in conn.query("EXPLAIN (ANALYZE, VERBOSE) " + sql.strip().rstrip(";"))[1])
        (exdir / f"{qid.split('(')[0]}.txt").write_text(f"-- {qid} @ {where}, trễ {label} ms\n{sql}\n\n{plan}\n", encoding="utf-8")
        nfs, touched = sites_touched(plan, where)
        ok = rows == ref_rows
        print(f"{qid:<22}{where:<10}{med:>12.2f}{len(rows):>7}{'✓' if ok else '✗':>6}{nfs:>7}  {','.join(touched)}")
        out_rows.append([now, label, qid, where, *[f"{t:.2f}" for t in times], f"{med:.2f}",
                         len(rows), ok, nfs, "+".join(touched), len(touched)])
    newfile = not (RESULTS / "results.csv").exists()
    with open(RESULTS / "results.csv", "a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        if newfile:
            w.writerow(["time", "delay_ms", "query", "run_at", *[f"run{i + 1}_ms" for i in range(RUNS)],
                        "median_ms", "rows", "equal_ref", "foreign_scans", "sites_touched", "n_sites"])
        w.writerows(out_rows)

    if label == "0":
        n1(central); n4(central); n5(ref)
    for c in (ref, central, dalat):
        c.close()


def n1(central):
    """N1: số dòng mỗi mảnh, đọc thẳng từng trạm, so với tổng tập trung."""
    exp = json.loads((SITE_DIR / "expected.json").read_text(encoding="utf-8"))
    rows = []
    for s in SITES:
        with connect(s) as c:
            q = " UNION ALL ".join(f"SELECT '{t}', count(*) FROM {t}" for t in ALL_TABLES)
            for t, n in c.query(q)[1]:
                rows.append([s, site(s)["machine"], t, n, exp["rows_per_site"][s][t]])
    with open(RESULTS / "n1.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh); w.writerow(["site", "machine", "table", "rows", "expected"]); w.writerows(rows)
    print("N1 → results/n1.csv")


def n4(central):
    """N4: tỉ lệ dòng liên vùng = booking thuộc đoàn có phòng ở >= 2 vùng."""
    sql = """
    WITH g AS (SELECT b.tour_group_id, count(DISTINCT h.region) AS nreg
               FROM all_booking b JOIN all_room r ON r.room_id = b.room_id JOIN all_hotel h ON h.hotel_id = r.hotel_id
               WHERE b.tour_group_id IS NOT NULL GROUP BY 1)
    SELECT (SELECT count(*) FROM all_booking) AS total,
           (SELECT count(*) FROM all_booking WHERE guest_type = 'tour') AS tour,
           (SELECT count(*) FROM all_booking b JOIN g USING (tour_group_id) WHERE g.nreg >= 2) AS cross_rows,
           (SELECT count(*) FROM g WHERE nreg >= 2) AS multi_groups,
           (SELECT count(*) FROM g WHERE nreg = 1) AS single_groups,
           (SELECT count(*) FROM g WHERE nreg = 3) AS three_region_groups"""
    cols, rows = central.query(sql)
    d = dict(zip(cols, rows[0])); d["rate"] = round(d["cross_rows"] / d["total"], 4)
    summ = json.loads((DATA_DIR / "summary.json").read_text(encoding="utf-8"))["cross_site"]
    d["summary_json_rows"] = summ["rows"]; d["summary_json_rate"] = summ["rate"]
    with open(RESULTS / "n4.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh); w.writerow(d.keys()); w.writerow(d.values())
    print(f"N4: {d['cross_rows']}/{d['total']} = {d['rate']:.2%} dòng liên vùng (summary.json: {summ['rows']}) → results/n4.csv")


def n5(ref):
    """N5: dung lượng jsonb so với bản quan hệ, có/không chỉ mục GIN (đo trên CSDL đối chứng)."""
    rows = []
    def add(k, v, note=""):
        rows.append([k, v, note])
    q = lambda s: ref.scalar(s)
    add("booking.request: tổng pg_column_size (byte)", q("SELECT sum(pg_column_size(request)) FROM booking"))
    add("booking.request: trung bình mỗi dòng (byte)", q("SELECT round(avg(pg_column_size(request)),1) FROM booking"))
    add("booking: heap có cột jsonb (byte)", q("SELECT pg_relation_size('booking')"))
    rel = ["req_tour", "req_business", "req_family", "req_family_child"]
    add("bản quan hệ req_*: heap (byte)", q("SELECT " + "+".join(f"pg_relation_size('{t}')" for t in rel)))
    add("bản quan hệ req_*: heap + chỉ mục PK (byte)", q("SELECT " + "+".join(f"pg_total_relation_size('{t}')" for t in rel)))
    add("bản quan hệ req_*: tổng pg_column_size dữ liệu (byte)", q(
        "SELECT (SELECT sum(pg_column_size(t.*)) FROM req_tour t) + (SELECT sum(pg_column_size(t.*)) FROM req_business t)"
        " + (SELECT sum(pg_column_size(t.*)) FROM req_family t) + (SELECT sum(pg_column_size(t.*)) FROM req_family_child t)"))
    q4 = load_sql("ref/q4.sql"); q5 = load_sql("ref/q5.sql")
    t_q4 = statistics.median(timed(ref, q4)[0][1:]); t_q5 = statistics.median(timed(ref, q5)[0][1:])
    add("Q4 (jsonb) trên đối chứng, không GIN (ms)", round(t_q4, 2))
    add("Q5 (quan hệ) trên đối chứng (ms)", round(t_q5, 2))
    for opclass in ["jsonb_ops", "jsonb_path_ops"]:
        ref.execute(f"DROP INDEX IF EXISTS booking_request_gin; CREATE INDEX booking_request_gin ON booking USING gin (request {opclass}); ANALYZE booking")
        add(f"GIN ({opclass}) trên booking.request (byte)", q("SELECT pg_relation_size('booking_request_gin')"))
        t = statistics.median(timed(ref, q4)[0][1:])
        plan = "\n".join(r[0] for r in ref.query("EXPLAIN " + q4.strip().rstrip(";"))[1])
        add(f"Q4 có GIN ({opclass}) (ms)", round(t, 2), "dùng GIN" if "booking_request_gin" in plan else "planner không dùng GIN")
    ref.execute("DROP INDEX IF EXISTS booking_request_gin; ANALYZE booking")
    with open(RESULTS / "n5.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh); w.writerow(["metric", "value", "note"]); w.writerows(rows)
    print("N5 → results/n5.csv")
    for r in rows:
        print(f"   {r[0]:<55}{r[1]!s:>12}  {r[2]}")


if __name__ == "__main__":
    main()
