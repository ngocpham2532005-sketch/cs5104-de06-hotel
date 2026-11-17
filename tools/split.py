#!/usr/bin/env python3
"""Chia CSV tập trung (output của generate.py) thành mảnh cho từng trạm, đúng thiết kế phân tán.

    python tools/split.py [--size lab|mini]
Kết quả: build/fragments/<size>/<trạm>/<bảng>.csv và build/fragments/<size>/expected.json
"""
import argparse
import csv
import json
from pathlib import Path

from common import ALL_TABLES, REPLICATED, ROOT, SITES_ORDER, Config

csv.field_size_limit(10_000_000)


def read(path: Path):
    with open(path, newline="", encoding="utf-8") as f:
        r = csv.reader(f)
        header = next(r)
        return header, list(r)


def split(size: str) -> dict:
    src = ROOT / "datagen" / "de06_hotel" / "output" / size
    if not (src / "booking.csv").exists():
        raise SystemExit(f"Chưa có dữ liệu {src}. Chạy `make data` trước.")
    out = ROOT / "build" / "fragments" / size
    data = {t: read(src / f"{t}.csv") for t in ALL_TABLES}

    # 1) vị trí (trạm) của từng dòng — phân mảnh ngang chính rồi dẫn xuất theo chuỗi khoá ngoại
    h_hdr, hotels = data["hotel"]
    site_of_hotel = {r[0]: r[h_hdr.index("region")] for r in hotels}
    r_hdr, rooms = data["room"]
    site_of_room = {r[0]: site_of_hotel[r[r_hdr.index("hotel_id")]] for r in rooms}
    b_hdr, bookings = data["booking"]
    site_of_booking = {r[0]: site_of_room[r[b_hdr.index("room_id")]] for r in bookings}

    def site_of(table, row, hdr):
        if table == "hotel":
            return site_of_hotel[row[0]]
        if table == "room":
            return site_of_room[row[0]]
        return site_of_booking[row[hdr.index("booking_id")]]  # booking và req_*

    # 2) ghi mảnh
    counts = {s: {} for s in SITES_ORDER}
    for s in SITES_ORDER:
        (out / s).mkdir(parents=True, exist_ok=True)
    for t in ALL_TABLES:
        hdr, rows = data[t]
        buckets = {s: [] for s in SITES_ORDER}
        for row in rows:
            if t in REPLICATED:
                for s in SITES_ORDER:
                    buckets[s].append(row)
            else:
                buckets[site_of(t, row, hdr)].append(row)
        for s in SITES_ORDER:
            with open(out / s / f"{t}.csv", "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(hdr)
                w.writerows(buckets[s])
            counts[s][t] = len(buckets[s])

    # 3) dòng liên vùng (theo định nghĩa trong summary.json)
    tg_idx = b_hdr.index("tour_group_id")
    regions_of_group = {}
    for row in bookings:
        if row[tg_idx]:
            regions_of_group.setdefault(row[tg_idx], set()).add(site_of_booking[row[0]])
    multi = {g for g, v in regions_of_group.items() if len(v) >= 2}
    cross = sum(1 for row in bookings if row[tg_idx] in multi)

    expected = {"size": size, "fragments": counts,
                "totals": {t: len(data[t][1]) for t in ALL_TABLES},
                "cross_site_rows": cross, "multi_region_groups": len(multi)}
    (out / "expected.json").write_text(json.dumps(expected, indent=2, ensure_ascii=False), encoding="utf-8")
    return expected


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--size", default=None)
    a = ap.parse_args()
    size = a.size or Config().size
    e = split(size)
    print(f"Đã chia dữ liệu cỡ {size} -> build/fragments/{size}/")
    print(f"  {'bảng':<18}" + "".join(f"{s:>10}" for s in SITES_ORDER) + f"{'tổng':>10}")
    for t in ALL_TABLES:
        vals = [e["fragments"][s][t] for s in SITES_ORDER]
        mark = "  (sao chép)" if t in REPLICATED else ""
        print(f"  {t:<18}" + "".join(f"{v:>10}" for v in vals) + f"{e['totals'][t]:>10}{mark}")
    print(f"  dòng liên vùng: {e['cross_site_rows']} ({e['multi_region_groups']} đoàn đi ≥ 2 vùng)")


if __name__ == "__main__":
    main()
