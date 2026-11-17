#!/usr/bin/env python3
"""Chạy nhanh Q1–Q5 cho buổi demo (D3, D4, D5, D6): kết quả, thời gian, so với đối chứng, Remote SQL.

    python tools/demo.py              # Q1..Q5
    python tools/demo.py Q2 Q3 -e     # chỉ Q2, Q3 và in các dòng Foreign Scan / Remote SQL của EXPLAIN (VERBOSE)
Thời gian: chạy 3 lần trong một phiên psql ngay trong container, lấy lần cuối (lần đầu gồm mở kết nối fdw).
"""
import re
import sys

import delay
from bench import fetch
from common import SQL_DIR, Config, docker_psql

Q = SQL_DIR / "queries"
SPEC = {"Q1": ("dalat", "q1_site.sql", "q1_ref.sql"), "Q2": ("central", "q2.sql", "q2_ref.sql"),
        "Q3": ("central", "q3.sql", "q3_ref.sql"), "Q4": ("central", "q4.sql", "q4_ref.sql"),
        "Q5": ("central", "q5.sql", "q5_ref.sql")}


def main():
    cfg = Config()
    args = [a.upper() for a in sys.argv[1:] if not a.startswith("-")] or list(SPEC)
    show_plan = "-e" in sys.argv or "--explain" in sys.argv
    print(f"trễ mạng hiện tại: {'BẬT +%d ms' % cfg.delay_ms if delay.is_on(cfg) else 'TẮT'}\n")
    ref = cfg.connect("ref")
    for q in args:
        where, f, fref = SPEC[q]
        node = cfg.central if where == "central" else where
        sql = (Q / f).read_text(encoding="utf-8")
        out = docker_psql(cfg, node, sql="\\timing on\n\\o /dev/null\n" + (sql.strip().rstrip(";") + ";\n") * 3)
        t = float(re.findall(r"Time: ([0-9.]+) ms", out)[-1])
        with cfg.connect(node) as c:
            got = fetch(c, sql)
            plan = [r[0] for r in c.execute("EXPLAIN (VERBOSE, COSTS OFF) " + sql.strip().rstrip(";")).fetchall()]
        exp = fetch(ref, (Q / fref).read_text(encoding="utf-8"))
        fs = [p for p in plan if "Foreign Scan" in p]
        print(f"== {q} @ {cfg.label(node)}")
        print(f"   {len(got)} dòng · {t:.2f} ms · giống CSDL đối chứng: {'CÓ ✓' if got == exp else 'KHÔNG ✗'} · "
              f"Foreign Scan: {len(fs)}" + (" (chạy trọn tại một trạm)" if not fs else ""))
        for r in got[:5]:
            print("     ", " | ".join(r))
        if len(got) > 5:
            print("      ...")
        if show_plan:
            for p in plan:
                if re.search(r"Foreign Scan|Relations:|Remote SQL:", p):
                    print("   ", p.strip()[:240])
        print()
    ref.close()


if __name__ == "__main__":
    main()
