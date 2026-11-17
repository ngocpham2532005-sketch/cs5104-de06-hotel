-- Q2 (biến thể so sánh): mỗi phần là kết nối 3 bảng ngoài của cùng một trạm.
-- Không bật use_remote_estimate, bộ tối ưu chỉ đẩy room⋈hotel, kéo booking về (xem N2/N3).
SELECT s.region, s.room_type_code, rt.name AS room_type,
       sum(s.revenue) AS revenue, sum(s.bookings)::bigint AS bookings
FROM (
    -- nhatrang (cục bộ)
    SELECT h.region, r.room_type_code, sum(b.nights * r.rate) AS revenue, count(*) AS bookings
    FROM public.booking b JOIN public.room r ON r.room_id = b.room_id JOIN public.hotel h ON h.hotel_id = r.hotel_id
    WHERE b.check_in >= DATE '2025-01-01' AND b.check_in < DATE '2026-01-01'
    GROUP BY h.region, r.room_type_code
    UNION ALL
    -- dalat
    SELECT h.region, r.room_type_code, sum(b.nights * r.rate) AS revenue, count(*) AS bookings
    FROM s_dalat.booking b JOIN s_dalat.room r ON r.room_id = b.room_id JOIN s_dalat.hotel h ON h.hotel_id = r.hotel_id
    WHERE b.check_in >= DATE '2025-01-01' AND b.check_in < DATE '2026-01-01'
    GROUP BY h.region, r.room_type_code
    UNION ALL
    -- phuquoc
    SELECT h.region, r.room_type_code, sum(b.nights * r.rate) AS revenue, count(*) AS bookings
    FROM s_phuquoc.booking b JOIN s_phuquoc.room r ON r.room_id = b.room_id JOIN s_phuquoc.hotel h ON h.hotel_id = r.hotel_id
    WHERE b.check_in >= DATE '2025-01-01' AND b.check_in < DATE '2026-01-01'
    GROUP BY h.region, r.room_type_code
    UNION ALL
    -- danang
    SELECT h.region, r.room_type_code, sum(b.nights * r.rate) AS revenue, count(*) AS bookings
    FROM s_danang.booking b JOIN s_danang.room r ON r.room_id = b.room_id JOIN s_danang.hotel h ON h.hotel_id = r.hotel_id
    WHERE b.check_in >= DATE '2025-01-01' AND b.check_in < DATE '2026-01-01'
    GROUP BY h.region, r.room_type_code
) s
JOIN room_type rt ON rt.room_type_code = s.room_type_code
GROUP BY s.region, s.room_type_code, rt.name
ORDER BY s.region, s.room_type_code;
