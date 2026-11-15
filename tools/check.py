"""
make check — kiểm tra ba quy tắc đúng đắn và mọi khoá chính, khoá ngoại trên toàn hệ.

Phần A (đọc thẳng từng trạm): vị từ mảnh, mảnh dẫn xuất, dải khoá chính của dòng mới,
        nhất quán jsonb ↔ bản quan hệ (tính chất cục bộ vì booking và req_* cùng trạm).
Phần B (tại trạm trung tâm, qua postgres_fdw): đầy đủ, tái tạo được (so với CSDL đối chứng),
        rời nhau, bảng sao chép giống nhau ở mọi trạm, khoá ngoại toàn hệ.
Mỗi kiểm tra là một câu SQL trả về SỐ DÒNG VI PHẠM (0 = đạt). Ghi kết quả vào results/check.txt.
"""
import sys, time
from cfg import (CENTRAL, PK, REPLICATED, FRAGMENTED, RESULTS, SITES, connect, site)


def local_checks(s, no):
    yield "vị từ mảnh hotel", f"SELECT count(*) FROM hotel WHERE region <> '{s}'"
    yield "dẫn xuất room ⋉ hotel", "SELECT count(*) FROM room r WHERE NOT EXISTS (SELECT 1 FROM hotel h WHERE h.hotel_id = r.hotel_id)"
    yield "dẫn xuất booking ⋉ room", "SELECT count(*) FROM booking b WHERE NOT EXISTS (SELECT 1 FROM room r WHERE r.room_id = b.room_id)"
    for t in ["req_tour", "req_business", "req_family"]:
        yield f"dẫn xuất {t} ⋉ booking", f"SELECT count(*) FROM {t} x WHERE NOT EXISTS (SELECT 1 FROM booking b WHERE b.booking_id = x.booking_id)"
    yield "dẫn xuất req_family_child ⋉ req_family", "SELECT count(*) FROM req_family_child c WHERE NOT EXISTS (SELECT 1 FROM req_family f WHERE f.booking_id = c.booking_id)"
    yield "dải khoá dòng mới (đuôi = site_no)", (
        f"SELECT (SELECT count(*) FROM hotel WHERE hotel_id >= 1000000 AND hotel_id % 10 <> {no})"
        f" + (SELECT count(*) FROM room WHERE room_id >= 1000000 AND room_id % 10 <> {no})"
        f" + (SELECT count(*) FROM booking WHERE booking_id >= 1000000 AND booking_id % 10 <> {no})")
    yield "CHECK mảnh + CHECK jsonb còn hiệu lực", (
        "SELECT 3 - count(*) FROM pg_constraint WHERE convalidated AND conname IN "
        "('frag_hotel_region','booking_request_shape','pk_range_booking') "
        "AND conrelid IN ('public.hotel'::regclass, 'public.booking'::regclass)")
    yield "jsonb ↔ req_tour", """
        SELECT count(*) FROM booking b FULL JOIN req_tour t ON t.booking_id = b.booking_id AND b.guest_type = 'tour'
        WHERE (b.guest_type = 'tour' OR t.booking_id IS NOT NULL)
          AND (b.booking_id IS NULL OR t.booking_id IS NULL
               OR t.group_code IS DISTINCT FROM b.request->>'group_code'
               OR t.meal_plan  IS DISTINCT FROM b.request->>'meal_plan'
               OR t.guide_room IS DISTINCT FROM (b.request->>'guide_room')::boolean)"""
    yield "jsonb ↔ req_business", """
        SELECT count(*) FROM booking b FULL JOIN req_business t ON t.booking_id = b.booking_id AND b.guest_type = 'business'
        WHERE (b.guest_type = 'business' OR t.booking_id IS NOT NULL)
          AND (b.booking_id IS NULL OR t.booking_id IS NULL
               OR t.company IS DISTINCT FROM b.request->>'company'
               OR t.tax_code IS DISTINCT FROM b.request->>'tax_code'
               OR t.late_checkout IS DISTINCT FROM (b.request->>'late_checkout')::boolean)"""
    yield "jsonb ↔ req_family", """
        SELECT count(*) FROM booking b FULL JOIN req_family t ON t.booking_id = b.booking_id AND b.guest_type = 'family'
        WHERE (b.guest_type = 'family' OR t.booking_id IS NOT NULL)
          AND (b.booking_id IS NULL OR t.booking_id IS NULL
               OR t.extra_bed IS DISTINCT FROM (b.request->>'extra_bed')::boolean
               OR t.airport_pickup IS DISTINCT FROM (b.request->>'airport_pickup')::boolean)"""
    yield "jsonb children_ages ↔ req_family_child", """
        WITH j AS (SELECT b.booking_id, e.ord::smallint AS seq, e.val::text::smallint AS age
                   FROM booking b, jsonb_array_elements(b.request->'children_ages') WITH ORDINALITY e(val, ord)
                   WHERE b.guest_type = 'family'),
             r AS (SELECT booking_id, seq, age FROM req_family_child)
        SELECT (SELECT count(*) FROM (SELECT * FROM j EXCEPT SELECT * FROM r) x)
             + (SELECT count(*) FROM (SELECT * FROM r EXCEPT SELECT * FROM j) y)"""


def cols(t):
    return ", ".join(PK[t])


def central_checks():
    for t in FRAGMENTED:
        yield f"đầy đủ: |all_{t}| = |đối chứng|", f"SELECT abs((SELECT count(*) FROM all_{t}) - (SELECT count(*) FROM ref.{t}))"
        yield f"tái tạo: all_{t} = đối chứng", (
            f"SELECT (SELECT count(*) FROM (SELECT * FROM all_{t} EXCEPT ALL SELECT * FROM ref.{t}) a)"
            f" + (SELECT count(*) FROM (SELECT * FROM ref.{t} EXCEPT ALL SELECT * FROM all_{t}) b)")
        yield f"rời nhau: khoá ({cols(t)}) không trùng giữa các trạm", (
            f"SELECT count(*) - count(DISTINCT ({cols(t)})) FROM all_{t}")
    for t in REPLICATED:
        for s in SITES:
            if s == CENTRAL:
                continue
            yield f"sao chép: {t} ở {s} = ở {CENTRAL}", (
                f"SELECT (SELECT count(*) FROM (SELECT * FROM s_{s}.{t} EXCEPT SELECT * FROM public.{t}) a)"
                f" + (SELECT count(*) FROM (SELECT * FROM public.{t} EXCEPT SELECT * FROM s_{s}.{t}) b)")
        yield f"sao chép: {t} = đối chứng", (
            f"SELECT (SELECT count(*) FROM (SELECT * FROM ref.{t} EXCEPT SELECT * FROM public.{t}) a)"
            f" + (SELECT count(*) FROM (SELECT * FROM public.{t} EXCEPT SELECT * FROM ref.{t}) b)")
    fks = [("room.hotel_id → hotel", "all_room", "hotel_id", "all_hotel", "hotel_id"),
           ("room.room_type_code → room_type", "all_room", "room_type_code", "room_type", "room_type_code"),
           ("booking.room_id → room", "all_booking", "room_id", "all_room", "room_id"),
           ("booking.tour_group_id → tour_group", "all_booking", "tour_group_id", "tour_group", "tour_group_id"),
           ("req_tour.booking_id → booking", "all_req_tour", "booking_id", "all_booking", "booking_id"),
           ("req_business.booking_id → booking", "all_req_business", "booking_id", "all_booking", "booking_id"),
           ("req_family.booking_id → booking", "all_req_family", "booking_id", "all_booking", "booking_id"),
           ("req_family_child.booking_id → req_family", "all_req_family_child", "booking_id", "all_req_family", "booking_id")]
    for name, ct, cc, pt, pc in fks:
        yield f"khoá ngoại toàn hệ {name}", (
            f"SELECT count(*) FROM {ct} c WHERE c.{cc} IS NOT NULL AND c.{cc} NOT IN (SELECT {pc} FROM {pt})")


def run(conn, label, checks, out):
    bad = 0
    for name, sql in checks:
        try:
            v = conn.scalar(sql)
        except Exception as e:  # noqa: BLE001
            v = f"LỖI {e}"
        ok = v == 0
        bad += not ok
        line = f"  {'✓' if ok else '✗'} {label:<9} {name:<58} vi phạm = {v}"
        print(line); out.append(line)
    return bad


def main():
    t0 = time.time(); out = []; bad = 0
    print("A. Kiểm tra cục bộ tại từng trạm (kết nối thẳng)"); out.append("A. cục bộ")
    for s in SITES:
        try:
            with connect(s, connect_timeout=3) as c:
                bad += run(c, s, local_checks(s, site(s)["site_no"]), out)
        except OSError as e:
            print(f"  ✗ {s}: không kết nối được ({e})"); bad += 1
    print(f"B. Kiểm tra toàn hệ tại trạm trung tâm {CENTRAL} (qua postgres_fdw)"); out.append("B. toàn hệ")
    with connect(CENTRAL) as c:
        bad += run(c, "toàn hệ", central_checks(), out)
    summary = f"KẾT QUẢ: {'ĐẠT' if bad == 0 else f'{bad} kiểm tra KHÔNG đạt'} ({time.time() - t0:.1f} s)"
    print(summary); out.append(summary)
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "check.txt").write_text("\n".join(out) + "\n", encoding="utf-8")
    sys.exit(0 if bad == 0 else 1)


if __name__ == "__main__":
    main()
