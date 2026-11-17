-- Q2 · Doanh thu theo vùng và loại phòng, năm 2025 (gộp 4 trạm) — chạy ở trạm trung tâm
-- Doanh thu của một lượt đặt = nights × room.rate; lượt đặt thuộc năm 2025 theo check_in.
-- GỘP HAI GIAI ĐOẠN (Giáo trình Mã 3.2):
--   giai đoạn 1 — mỗi trạm tự lọc + GROUP BY trên khung nhìn cục bộ booking_detail (booking⋈room⋈hotel);
--                postgres_fdw đẩy nguyên WHERE + GROUP BY xuống (Relations: Aggregate on ...),
--                3 trạm xa được hỏi SONG SONG (Async Foreign Scan), mỗi trạm trả ≤ 15 dòng;
--   giai đoạn 2 — trạm trung tâm cộng dồn và nối room_type (bản sao cục bộ) để lấy tên loại phòng.
SELECT s.region, s.room_type_code, rt.name AS room_type,
       sum(s.revenue) AS revenue, sum(s.bookings)::bigint AS bookings
FROM (
    -- nhatrang (cục bộ)
    SELECT region, room_type_code, sum(nights * rate) AS revenue, count(*) AS bookings
    FROM public.booking_detail
    WHERE check_in >= DATE '2025-01-01' AND check_in < DATE '2026-01-01'
    GROUP BY region, room_type_code
    UNION ALL
    -- dalat
    SELECT region, room_type_code, sum(nights * rate) AS revenue, count(*) AS bookings
    FROM s_dalat.booking_detail
    WHERE check_in >= DATE '2025-01-01' AND check_in < DATE '2026-01-01'
    GROUP BY region, room_type_code
    UNION ALL
    -- phuquoc
    SELECT region, room_type_code, sum(nights * rate) AS revenue, count(*) AS bookings
    FROM s_phuquoc.booking_detail
    WHERE check_in >= DATE '2025-01-01' AND check_in < DATE '2026-01-01'
    GROUP BY region, room_type_code
    UNION ALL
    -- danang
    SELECT region, room_type_code, sum(nights * rate) AS revenue, count(*) AS bookings
    FROM s_danang.booking_detail
    WHERE check_in >= DATE '2025-01-01' AND check_in < DATE '2026-01-01'
    GROUP BY region, room_type_code
) s
JOIN room_type rt ON rt.room_type_code = s.room_type_code
GROUP BY s.region, s.room_type_code, rt.name
ORDER BY s.region, s.room_type_code;
