#!/usr/bin/env python3
"""make check — kiểm tra tính đúng đắn của hệ phân tán (demo D2).

A. Ba quy tắc đúng đắn cho 7 bảng bị chia (ở trạm trung tâm, so với CSDL đối chứng qua postgres_fdw):
   đầy đủ (không thiếu dòng), tái tạo được (UNION ALL các mảnh EXCEPT ALL bảng gốc = ∅, hai chiều),
   rời nhau (không khoá nào nằm ở hai trạm).
B. Bảng sao chép: mỗi bản sao ở mỗi trạm giống hệt bảng gốc.
C. Đúng mảnh tại từng trạm (đọc thẳng trạm): vị từ của mảnh, khoá ngoại cục bộ, dải khoá chính.
D. Khoá chính, khoá ngoại trên toàn hệ (trên all_*).
E. jsonb ↔ bản quan hệ nhất quán (từng trạm, hai chiều EXCEPT ALL).
F. Dữ liệu gốc của bộ sinh khớp summary.json (chỉ đếm dòng có id của bộ sinh, nên vẫn đúng sau khi nhập thêm).
Mọi truy vấn kiểm tra mong đợi kết quả 0. Kết quả ghi results/check.txt; mã thoát ≠ 0 nếu có lỗi.
"""
import json
import sys
import time

from common import FRAGMENTED, PK, REPLICATED, RESULTS, ROOT, SITES_ORDER, Config

LOG = []


def report(passed: bool, name: str, detail: str = ""):
    line = f"  [{'OK' if passed else 'FAIL':<4}] {name}" + (f"  ({detail})" if detail else "")
    print(line, flush=True)
    LOG.append(line)
    return passed


def zero(conn, name: str, sql: str) -> bool:
    v = conn.execute(sql).fetchone()[0]
    return report(v == 0, name, f"= {v}")


def main():
    cfg = Config()
    t0 = time.time()
    bad = 0
    central = cfg.connect(cfg.central, timeout=5)
    remote = cfg.remote_sites()

    def site_tables(t):  # (tên trạm, bảng) cho mọi trạm, nhìn từ trạm trung tâm
        return [(cfg.central, f"public.{t}")] + [(s, f"s_{s}.{t}") for s in remote]

    print("A. Ba quy tắc đúng đắn (7 bảng bị chia)")
    for t in FRAGMENTED:
        pk = PK[t]
        on = " AND ".join(f"a.{k} = r.{k}" for k in pk)
        bad += not zero(central, f"{t:<17} đầy đủ      : dòng của ref không có ở trạm nào",
                        f"SELECT count(*) FROM ref.{t} r WHERE NOT EXISTS (SELECT 1 FROM all_{t} a WHERE {on})")
        bad += not zero(central, f"{t:<17} tái tạo     : ref EXCEPT ALL (∪ mảnh)",
                        f"SELECT count(*) FROM (SELECT * FROM ref.{t} EXCEPT ALL SELECT * FROM all_{t}) x")
        bad += not zero(central, f"{t:<17} tái tạo     : (∪ mảnh) EXCEPT ALL ref",
                        f"SELECT count(*) FROM (SELECT * FROM all_{t} EXCEPT ALL SELECT * FROM ref.{t}) x")
        keys = ", ".join(pk)
        bad += not zero(central, f"{t:<17} rời nhau    : khoá nằm ở ≥ 2 trạm",
                        f"SELECT count(*) FROM (SELECT {keys} FROM all_{t} GROUP BY {keys} HAVING count(*) > 1) x")

    print("B. Bảng sao chép giống hệt bảng gốc ở mọi trạm")
    for t in REPLICATED:
        for s, rel in site_tables(t):
            bad += not zero(central, f"{t:<17} @ {s:<9}: bản sao ≠ ref (hai chiều)",
                            f"SELECT (SELECT count(*) FROM (SELECT * FROM ref.{t} EXCEPT ALL SELECT * FROM {rel}) a)"
                            f"     + (SELECT count(*) FROM (SELECT * FROM {rel} EXCEPT ALL SELECT * FROM ref.{t}) b)")

    print("C. Đúng mảnh tại từng trạm (đọc thẳng từng trạm)")
    for s in SITES_ORDER:
        no = cfg.sites[s]["no"]
        lo, hi = no * 10_000_000 + 1, (no + 1) * 10_000_000 - 1
        with cfg.connect(s) as c:
            checks = {
                "hotel.region ≠ vùng của trạm": f"SELECT count(*) FROM hotel WHERE region <> '{s}'",
                "room mồ côi (hotel không ở trạm)": "SELECT count(*) FROM room r WHERE NOT EXISTS (SELECT 1 FROM hotel h WHERE h.hotel_id = r.hotel_id)",
                "booking mồ côi (room không ở trạm)": "SELECT count(*) FROM booking b WHERE NOT EXISTS (SELECT 1 FROM room r WHERE r.room_id = b.room_id)",
                "req_* mồ côi (booking không ở trạm)": "SELECT (SELECT count(*) FROM req_tour x WHERE NOT EXISTS (SELECT 1 FROM booking b WHERE b.booking_id = x.booking_id))"
                    " + (SELECT count(*) FROM req_business x WHERE NOT EXISTS (SELECT 1 FROM booking b WHERE b.booking_id = x.booking_id))"
                    " + (SELECT count(*) FROM req_family x WHERE NOT EXISTS (SELECT 1 FROM booking b WHERE b.booking_id = x.booking_id))",
                "req_family_child mồ côi": "SELECT count(*) FROM req_family_child c WHERE NOT EXISTS (SELECT 1 FROM req_family f WHERE f.booking_id = c.booking_id)",
                "booking_id mới ngoài dải của trạm": f"SELECT count(*) FROM booking WHERE booking_id >= 10000000 AND booking_id NOT BETWEEN {lo} AND {hi}",
                "CHECK/FK khai báo nhưng chưa VALID": "SELECT count(*) FROM pg_constraint WHERE NOT convalidated AND connamespace = 'public'::regnamespace",
            }
            for name, sql in checks.items():
                bad += not zero(c, f"{s:<9} {name}", sql)

    print("D. Khoá chính, khoá ngoại trên toàn hệ")
    fks = {
        "room.hotel_id → hotel": "SELECT count(*) FROM all_room r WHERE NOT EXISTS (SELECT 1 FROM all_hotel h WHERE h.hotel_id = r.hotel_id)",
        "room.room_type_code → room_type": "SELECT count(*) FROM all_room r WHERE NOT EXISTS (SELECT 1 FROM room_type t WHERE t.room_type_code = r.room_type_code)",
        "booking.room_id → room": "SELECT count(*) FROM all_booking b WHERE NOT EXISTS (SELECT 1 FROM all_room r WHERE r.room_id = b.room_id)",
        "booking.tour_group_id → tour_group": "SELECT count(*) FROM all_booking b WHERE b.tour_group_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM tour_group g WHERE g.tour_group_id = b.tour_group_id)",
        "req_tour → booking(tour)": "SELECT count(*) FROM all_req_tour x WHERE NOT EXISTS (SELECT 1 FROM all_booking b WHERE b.booking_id = x.booking_id AND b.guest_type = 'tour')",
        "req_business → booking(business)": "SELECT count(*) FROM all_req_business x WHERE NOT EXISTS (SELECT 1 FROM all_booking b WHERE b.booking_id = x.booking_id AND b.guest_type = 'business')",
        "req_family → booking(family)": "SELECT count(*) FROM all_req_family x WHERE NOT EXISTS (SELECT 1 FROM all_booking b WHERE b.booking_id = x.booking_id AND b.guest_type = 'family')",
        "req_family_child → req_family": "SELECT count(*) FROM all_req_family_child c WHERE NOT EXISTS (SELECT 1 FROM all_req_family f WHERE f.booking_id = c.booking_id)",
        "PK toàn hệ: room_type, tour_group trùng": "SELECT (SELECT count(*) - count(DISTINCT room_type_code) FROM room_type) + (SELECT count(*) - count(DISTINCT tour_group_id) FROM tour_group)",
    }
    for name, sql in fks.items():
        bad += not zero(central, name, sql)

    print("E. jsonb ↔ bản quan hệ nhất quán (từng trạm)")
    pairs = {
        "tour":     ("SELECT booking_id, request->>'group_code', request->>'meal_plan', (request->>'guide_room')::boolean FROM booking WHERE guest_type = 'tour'",
                     "SELECT booking_id, group_code, meal_plan, guide_room FROM req_tour"),
        "business": ("SELECT booking_id, request->>'company', request->>'tax_code', (request->>'late_checkout')::boolean FROM booking WHERE guest_type = 'business'",
                     "SELECT booking_id, company, tax_code, late_checkout FROM req_business"),
        "family":   ("SELECT booking_id, (request->>'extra_bed')::boolean, (request->>'airport_pickup')::boolean FROM booking WHERE guest_type = 'family'",
                     "SELECT booking_id, extra_bed, airport_pickup FROM req_family"),
        "children": ("SELECT b.booking_id, e.ord::smallint, e.age::smallint FROM booking b, "
                     "jsonb_array_elements_text(b.request->'children_ages') WITH ORDINALITY AS e(age, ord) WHERE b.guest_type = 'family'",
                     "SELECT booking_id, seq, age FROM req_family_child"),
    }
    for s in SITES_ORDER:
        with cfg.connect(s) as c:
            for k, (j, r) in pairs.items():
                bad += not zero(c, f"{s:<9} {k:<9} jsonb ⇄ quan hệ",
                                f"SELECT (SELECT count(*) FROM ({j} EXCEPT ALL {r}) a) + (SELECT count(*) FROM ({r} EXCEPT ALL {j}) b)")

    print("F. Dữ liệu gốc của bộ sinh khớp summary.json")
    summ = json.loads((ROOT / "datagen" / "de06_hotel" / "output" / cfg.size / "summary.json").read_text(encoding="utf-8"))
    gen_filter = {"booking": "booking_id < 10000000", "tour_group": "tour_group_id < 100001"}
    for t, n in summ["rows"].items():
        rel = f"all_{t}" if t in FRAGMENTED else t
        f = gen_filter.get(t) or ("booking_id < 10000000" if t.startswith("req_") else "true")
        v = central.execute(f"SELECT count(*) FROM {rel} WHERE {f}").fetchone()[0]
        bad += not report(v == n, f"{t:<17} số dòng gốc", f"{v} / summary.json {n}")
    for s in SITES_ORDER:
        rel = "public.hotel" if s == cfg.central else f"s_{s}.hotel"
        v = central.execute(f"SELECT count(*) FROM {rel}").fetchone()[0]
        n = summ["by_region"]["hotel.region"][s]
        bad += not report(v == n, f"hotel @ {s:<9}", f"{v} / summary.json {n}")
    v = central.execute("""
        WITH b AS (SELECT b.booking_id, b.tour_group_id, h.region
                   FROM all_booking b JOIN all_room r USING (room_id) JOIN all_hotel h USING (hotel_id)
                   WHERE b.booking_id < 10000000 AND b.tour_group_id IS NOT NULL),
             m AS (SELECT tour_group_id FROM b GROUP BY 1 HAVING count(DISTINCT region) >= 2)
        SELECT count(*) FROM b WHERE tour_group_id IN (SELECT tour_group_id FROM m)""").fetchone()[0]
    n = summ["cross_site"]["rows"]
    bad += not report(v == n, "dòng liên vùng (đoàn ≥ 2 vùng)", f"{v} / summary.json {n}")
    central.close()

    verdict = "ĐẠT" if bad == 0 else f"KHÔNG ĐẠT ({bad} lỗi)"
    LOG.append(f"\nKẾT LUẬN: {verdict} · {time.time() - t0:.1f}s")
    print(LOG[-1])
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "check.txt").write_text("\n".join(LOG) + "\n", encoding="utf-8")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
