#!/usr/bin/env python3
"""Nạp dữ liệu: CSDL đối chứng `ref` (lược đồ tập trung) + đúng mảnh vào từng trạm.

    python tools/load.py [--size lab|mini] [--wait 600]
1. Chờ mọi trạm (kể cả trạm ở máy B) nhận kết nối.
2. Chia CSV thành mảnh (tools/split.py).
3. ref: schema_central.sql + COPY toàn bộ CSV.
4. Mỗi trạm: site_schema.sql (đã thay tham số) + COPY mảnh của trạm; trạm trung tâm thêm sequence đoàn tour.
5. In bảng số dòng mỗi mảnh, so với dự kiến và summary.json -> results/n1_fragments.csv
"""
import argparse
import csv
import json
import sys
import time
from pathlib import Path

from common import (ALL_TABLES, ID_BLOCK, REPLICATED, RESULTS, ROOT, SITES_ORDER, SQL_DIR,
                    TOUR_GROUP_NEW_START, Config, die, fail, ok)
from split import split


def wait_all(cfg: Config, timeout: int):
    import psycopg
    pending = list(cfg.nodes())
    t0 = time.time()
    shown = set()
    while pending:
        for n in list(pending):
            try:
                with cfg.connect(n, timeout=2) as c:
                    c.execute("select 1")
                pending.remove(n)
                print(f"  kết nối được {cfg.label(n)}")
            except psycopg.Error:
                if n not in shown and cfg.machine_of(n) != cfg.here:
                    print(f"  đang chờ {cfg.label(n)} — hãy chạy `make all MACHINE={cfg.machine_of(n)}` trên máy đó")
                    shown.add(n)
        if pending and time.time() - t0 > timeout:
            die(f"không kết nối được: {', '.join(pending)}")
        if pending:
            time.sleep(2)


def copy_csv(conn, table: str, path: Path):
    with conn.cursor() as cur, open(path, "rb") as f:
        with cur.copy(f"COPY {table} FROM STDIN WITH (FORMAT csv, HEADER true)") as cp:
            while chunk := f.read(1 << 20):
                cp.write(chunk)


def load_ref(cfg: Config, src: Path):
    with cfg.connect("ref", autocommit=False) as c:
        c.execute((SQL_DIR / "schema_central.sql").read_text(encoding="utf-8"))
        for t in ALL_TABLES:
            copy_csv(c, t, src / f"{t}.csv")
        c.commit()
        c.autocommit = True
        c.execute("ANALYZE")
    print(f"  ref: đã nạp {len(ALL_TABLES)} bảng từ {src.relative_to(ROOT)}")


def site_sql(cfg: Config, site: str) -> str:
    no = cfg.sites[site]["no"]
    sql = (SQL_DIR / "site_schema.sql").read_text(encoding="utf-8")
    sql = (sql.replace("__SITE__", site)
              .replace("__ID_LO__", str(no * ID_BLOCK + 1))
              .replace("__ID_HI__", str((no + 1) * ID_BLOCK - 1)))
    if site == cfg.central:
        sql += f"\nCREATE SEQUENCE tour_group_id_seq START {TOUR_GROUP_NEW_START};  -- id đoàn tour mới (cấp ở trạm trung tâm)\n"
    return sql


def load_site(cfg: Config, site: str, frag: Path):
    with cfg.connect(site, autocommit=False) as c:
        # dọn phần liên kết cũ ở trạm trung tâm (khung nhìn all_* phụ thuộc bảng cục bộ)
        if site == cfg.central:
            c.execute("DROP SCHEMA IF EXISTS ref CASCADE")
            for s in cfg.remote_sites():
                c.execute(f"DROP SCHEMA IF EXISTS s_{s} CASCADE")
            for t in ALL_TABLES:
                c.execute(f"DROP VIEW IF EXISTS all_{t} CASCADE")
        c.execute(site_sql(cfg, site))
        for t in ALL_TABLES:
            copy_csv(c, t, frag / site / f"{t}.csv")
        c.commit()
        c.autocommit = True
        c.execute("ANALYZE")
        counts = {t: c.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in ALL_TABLES}
    print(f"  {site}: đã nạp mảnh ({counts['hotel']} khách sạn, {counts['room']} phòng, "
          f"{counts['booking']} lượt đặt) vào {cfg.label(site)}")
    return counts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--size", default=None)
    ap.add_argument("--wait", type=int, default=600)
    a = ap.parse_args()
    cfg = Config()
    size = a.size or cfg.size
    src = ROOT / "datagen" / "de06_hotel" / "output" / size
    frag = ROOT / "build" / "fragments" / size

    (RESULTS / "events.jsonl").unlink(missing_ok=True)   # nhật ký sự kiện của dashboard bắt đầu lại
    print("1) Chờ các trạm sẵn sàng")
    wait_all(cfg, a.wait)
    print("2) Chia dữ liệu thành mảnh")
    expected = split(size)
    print("3) Nạp CSDL đối chứng")
    load_ref(cfg, src)
    print("4) Nạp mảnh vào từng trạm")
    actual = {s: load_site(cfg, s, frag) for s in SITES_ORDER}

    print("5) Đối chiếu số dòng")
    summary = json.loads((src / "summary.json").read_text(encoding="utf-8"))
    bad = 0
    RESULTS.mkdir(exist_ok=True)
    with open(RESULTS / "n1_fragments.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["table", "kind"] + SITES_ORDER + ["sum_fragments", "ref_summary_json", "match"])
        for t in ALL_TABLES:
            vals = [actual[s][t] for s in SITES_ORDER]
            exp = [expected["fragments"][s][t] for s in SITES_ORDER]
            total = summary["rows"][t]
            if t in REPLICATED:
                match = all(v == total for v in vals)
                kind, sm = "replicated", vals[0]
            else:
                match = sum(vals) == total
                kind, sm = "fragmented", sum(vals)
            match = match and vals == exp
            w.writerow([t, kind] + vals + [sm, total, match])
            (ok if match else fail)(f"{t:<18} {vals}  tổng={sm}  summary.json={total}")
            bad += not match
    hreg = summary["by_region"]["hotel.region"]
    for s in SITES_ORDER:
        if actual[s]["hotel"] != hreg[s]:
            fail(f"hotel@{s}={actual[s]['hotel']} khác summary.json {hreg[s]}")
            bad += 1
    if expected["cross_site_rows"] == summary["cross_site"]["rows"]:
        ok(f"dòng liên vùng = {expected['cross_site_rows']} (rate {summary['cross_site']['rate']}) khớp summary.json")
    else:
        fail("số dòng liên vùng khác summary.json")
        bad += 1
    print("-> results/n1_fragments.csv")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
