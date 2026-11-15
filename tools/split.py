"""
Chia CSV tập trung (output/<size>/*.csv) thành mảnh cho từng trạm theo thiết kế:

  hotel            : ngang chính, vị từ region = '<trạm>'
  room             : ngang dẫn xuất theo hotel   (room ⋉ hotel_i)
  booking          : ngang dẫn xuất theo room    (booking ⋉ room_i)
  req_tour/business/family : dẫn xuất theo booking
  req_family_child : dẫn xuất theo req_family (cùng booking_id)
  room_type, tour_group : sao chép nguyên vẹn ra mọi trạm

Kết quả: output/<size>/sites/<trạm>/<bảng>.csv và output/<size>/sites/expected.json
"""
import csv, json, sys
from cfg import DATA_DIR, SITE_DIR, SITES, REPLICATED, FRAGMENTED


def read(table):
    with open(DATA_DIR / f"{table}.csv", newline="", encoding="utf-8") as f:
        r = csv.reader(f)
        return next(r), list(r)


def main():
    if not (DATA_DIR / "booking.csv").exists():
        sys.exit(f"Chưa có dữ liệu ở {DATA_DIR}. Chạy `make data` trước.")
    data = {t: read(t) for t in REPLICATED + FRAGMENTED}
    hotel_site = {row[0]: row[2] for row in data["hotel"][1]}            # hotel_id -> region
    room_site = {row[0]: hotel_site[row[1]] for row in data["room"][1]}  # room_id  -> region
    book_site = {row[0]: room_site[row[1]] for row in data["booking"][1]}
    site_of = {
        "hotel": lambda r: r[2],
        "room": lambda r: hotel_site[r[1]],
        "booking": lambda r: room_site[r[1]],
        "req_tour": lambda r: book_site[r[0]],
        "req_business": lambda r: book_site[r[0]],
        "req_family": lambda r: book_site[r[0]],
        "req_family_child": lambda r: book_site[r[0]],
    }
    expected = {s: {} for s in SITES}
    for s in SITES:
        (SITE_DIR / s).mkdir(parents=True, exist_ok=True)
    for t in REPLICATED + FRAGMENTED:
        header, rows = data[t]
        parts = {s: [] for s in SITES}
        for row in rows:
            if t in REPLICATED:
                for s in SITES:
                    parts[s].append(row)
            else:
                parts[site_of[t](row)].append(row)
        if t in FRAGMENTED:   # kiểm tra ngay: đầy đủ + rời nhau
            assert sum(len(p) for p in parts.values()) == len(rows), t
        for s in SITES:
            with open(SITE_DIR / s / f"{t}.csv", "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f); w.writerow(header); w.writerows(parts[s])
            expected[s][t] = len(parts[s])
    # dòng liên vùng: booking thuộc đoàn tour có phòng ở >= 2 vùng
    regions_of_group = {}
    for row in data["booking"][1]:
        if row[6]:
            regions_of_group.setdefault(row[6], set()).add(book_site[row[0]])
    multi = {g for g, r in regions_of_group.items() if len(r) >= 2}
    cross = {s: 0 for s in SITES}
    for row in data["booking"][1]:
        if row[6] in multi:
            cross[book_site[row[0]]] += 1
    out = {"size": DATA_DIR.name, "rows_per_site": expected,
           "total_central": {t: len(data[t][1]) for t in data},
           "cross_site_rows_per_site": cross, "cross_site_rows": sum(cross.values()),
           "multi_region_groups": len(multi)}
    (SITE_DIR / "expected.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"{'bảng':<18}" + "".join(f"{s:>10}" for s in SITES) + f"{'tập trung':>11}")
    for t in REPLICATED + FRAGMENTED:
        print(f"{t:<18}" + "".join(f"{expected[s][t]:>10}" for s in SITES) + f"{len(data[t][1]):>11}")
    print(f"dòng liên vùng: {out['cross_site_rows']} ({out['multi_region_groups']} đoàn đi nhiều vùng)")


if __name__ == "__main__":
    main()
