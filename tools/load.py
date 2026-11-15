"""
Nạp dữ liệu (chạy ở máy A):
  1. CSDL đối chứng hotel_ref (trong container trạm trung tâm) ← toàn bộ CSV tập trung.
  2. Mỗi trạm: CSDL hotel ← schema_central.sql + site_extra.sql + đúng mảnh của trạm.
  3. Đối chiếu số dòng với expected.json và summary.json.
"""
import json, sys, time
from cfg import (CENTRAL, DATA_DIR, DB, ROOT, SITE_DIR, SITES, ALL_TABLES, connect, site)

SCHEMA = (ROOT / "sql" / "schema_central.sql").read_text(encoding="utf-8")
EXTRA = (ROOT / "sql" / "site_extra.sql").read_text(encoding="utf-8")


def recreate(s, dbname):
    with connect(s, db="postgres") as c:
        c.execute(f'DROP DATABASE IF EXISTS "{dbname}" WITH (FORCE)')
        c.execute(f'CREATE DATABASE "{dbname}" TEMPLATE template0 ENCODING \'UTF8\'')


def copy_dir(c, d):
    counts = {}
    for t in ALL_TABLES:
        data = (d / f"{t}.csv").read_bytes()
        res = c.execute(f"COPY {t} FROM STDIN WITH (FORMAT csv, HEADER true)", copy_data=data)
        counts[t] = int(res[-1].status.split()[-1])
    c.execute("ANALYZE")
    return counts


def main():
    if not (SITE_DIR / "expected.json").exists():
        sys.exit("Chưa chia mảnh. Chạy `make data` trước.")
    expected = json.loads((SITE_DIR / "expected.json").read_text(encoding="utf-8"))
    summary = json.loads((DATA_DIR / "summary.json").read_text(encoding="utf-8"))
    ok = True
    t0 = time.time()
    # 1) CSDL đối chứng
    recreate(CENTRAL, DB["refdb"])
    with connect(CENTRAL, db=DB["refdb"]) as c:
        c.execute(SCHEMA)
        got = copy_dir(c, DATA_DIR)
    bad = {t: (got[t], summary["rows"][t]) for t in got if got[t] != summary["rows"][t]}
    print(f"[ref] {DB['refdb']} @ {CENTRAL}: {sum(got.values())} dòng  "
          + ("khớp summary.json" if not bad else f"LỆCH {bad}"))
    ok &= not bad
    # 2) từng trạm
    for s in SITES:
        info = site(s)
        recreate(s, DB["dbname"])
        with connect(s) as c:
            c.execute(SCHEMA)
            c.execute(EXTRA.replace("{{REGION}}", s).replace("{{SITE_NO}}", str(info["site_no"]))
                      .replace("{{DBNAME}}", DB["dbname"]))
            if info["central"]:
                # chỉ trạm trung tâm cấp mã đoàn tour mới (bảng sao chép)
                c.execute("CREATE SEQUENCE tour_group_id_seq START 1000000 INCREMENT 10")
            got = copy_dir(c, SITE_DIR / s)
        bad = {t: (got[t], expected["rows_per_site"][s][t]) for t in got
               if got[t] != expected["rows_per_site"][s][t]}
        print(f"[{s:<8}] máy {info['machine']} {info['ip']}:{info['port']}  "
              f"hotel={got['hotel']} room={got['room']} booking={got['booking']}  "
              + ("khớp" if not bad else f"LỆCH {bad}"))
        ok &= not bad
    print(f"Nạp xong sau {time.time() - t0:.1f} s")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
