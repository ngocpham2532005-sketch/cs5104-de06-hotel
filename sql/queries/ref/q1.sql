-- Q1 trên CSDL đối chứng
WITH rooms AS (
    SELECT r.hotel_id, count(*) AS n_rooms
    FROM room r GROUP BY r.hotel_id
), sold AS (
    -- số đêm của mỗi lượt đặt nằm trong tháng 7/2025 (cắt phần ngoài tháng)
    SELECT r.hotel_id,
           sum(least(b.check_in + b.nights, DATE '2025-08-01') - greatest(b.check_in, DATE '2025-07-01')) AS nights_sold
    FROM booking b JOIN room r ON r.room_id = b.room_id
    WHERE b.check_in < DATE '2025-08-01' AND b.check_in + b.nights > DATE '2025-07-01'
    GROUP BY r.hotel_id
), per AS (
    SELECT h.hotel_id, h.name, coalesce(s.nights_sold, 0) AS nights_sold, rm.n_rooms * 31 AS nights_available
    FROM hotel h
    JOIN rooms rm ON rm.hotel_id = h.hotel_id
    LEFT JOIN sold s ON s.hotel_id = h.hotel_id
    WHERE h.region = 'dalat'
)
SELECT hotel_id, name, nights_sold, nights_available,
       round(100.0 * nights_sold / nights_available, 2) AS occupancy_pct
FROM per
UNION ALL
SELECT NULL, 'TỔNG Đà Lạt', sum(nights_sold), sum(nights_available),
       round(100.0 * sum(nights_sold) / sum(nights_available), 2)
FROM per
ORDER BY hotel_id NULLS LAST;
