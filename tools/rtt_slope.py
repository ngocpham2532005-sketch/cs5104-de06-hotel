#!/usr/bin/env python3
"""Đo số vòng khứ hồi của từng truy vấn: chạy ở trễ 30 ms và 60 ms, số RTT = (T60 − T30) / 30.

Phần thời gian xử lý và RTT gốc của mạng bị triệt tiêu khi lấy hiệu, nên con số còn lại chỉ là
số lượt đi-về tuần tự trên đường bị trễ. Ghi ra results/rtt_slope.txt.

    make venv; .venv/bin/python tools/rtt_slope.py
"""
import statistics

import bench
import delay
from common import RESULTS, Config

CASES = [  # (nhãn, tệp truy vấn, tuỳ chọn server)
    ("Q2 two_phase", "q2.sql", {}),
    ("Q2 two_phase_no_async", "q2.sql", {"async_capable": "false"}),
    ("Q2 no_parallel_commit", "q2.sql", {"parallel_commit": "false"}),
    ("Q3 pushdown", "q3.sql", {}),
    ("Q4 jsonb", "q4.sql", {}),
    ("Q5 view", "q5.sql", {}),
]


def med(cfg, sql, opts):
    bench.set_opts(cfg, opts)
    try:
        return statistics.median(bench.timed_runs(cfg, cfg.central, sql)[1:])
    finally:
        bench.set_opts(cfg, opts, restore=True)


def main():
    cfg = Config()
    cases = [(f"PROBE {s}", f"SELECT capacity FROM s_{s}.room_type WHERE room_type_code = 'RT01'", {})
             for s in cfg.remote_sites()]
    cases += [(n, (bench.Q / f).read_text(encoding="utf-8"), o) for n, f, o in CASES]
    res = {}
    try:
        for d in (30, 60):
            cfg.delay_ms = d
            delay.on(cfg)
            for name, sql, opts in cases:
                res[(name, d)] = med(cfg, sql, opts)
                print(f"  {name:<24} trễ {d} ms  {res[(name, d)]:8.1f} ms", flush=True)
    finally:
        delay.off(cfg)
    lines = [f"{'truy vấn':<24}  T30 (ms)  T60 (ms)  số RTT = ΔT/30"]
    for name, _, _ in cases:
        a, b = res[(name, 30)], res[(name, 60)]
        lines.append(f"{name:<24} {a:9.1f} {b:9.1f} {(b - a) / 30:15.1f}")
    out = "\n".join(lines) + "\n"
    (RESULTS / "rtt_slope.txt").write_text(out, encoding="utf-8")
    print(out + "-> results/rtt_slope.txt")


if __name__ == "__main__":
    main()
