-- Q1 · Công suất phòng (số đêm đã bán / số đêm có thể bán) của khách sạn Đà Lạt, tháng 7/2025
-- Bản chạy trên CSDL đối chứng (lược đồ tập trung).
-- Đêm đã bán = phần giao của [check_in, check_in + nights) với [2025-07-01, 2025-08-01)
--   (lượt nhận phòng cuối tháng 6 kéo sang tháng 7 cũng được tính phần trong tháng 7).
-- Đêm có thể bán = số phòng × 31.
WITH sold AS (
    SELECT r.hotel_id,
           sum(least(b.check_in + b.nights, DATE '2025-08-01')
               - greatest(b.check_in, DATE '2025-07-01')) AS sold_nights
    FROM booking b JOIN room r ON r.room_id = b.room_id
    WHERE b.check_in < DATE '2025-08-01'
      AND b.check_in >= DATE '2025-07-01' - 60          -- nights <= 60 (CHECK) -> cho phép dùng chỉ mục check_in
      AND b.check_in + b.nights > DATE '2025-07-01'
    GROUP BY r.hotel_id),
cap AS (
    SELECT hotel_id, count(*) * 31 AS available_nights FROM room GROUP BY hotel_id)
SELECT h.hotel_id, h.name,
       coalesce(s.sold_nights, 0)::bigint AS sold_nights,
       c.available_nights::bigint         AS available_nights,
       round(100.0 * coalesce(s.sold_nights, 0) / c.available_nights, 2) AS occupancy_pct
FROM hotel h
JOIN cap c       ON c.hotel_id = h.hotel_id
LEFT JOIN sold s ON s.hotel_id = h.hotel_id
WHERE h.region = 'dalat'
ORDER BY h.hotel_id;
