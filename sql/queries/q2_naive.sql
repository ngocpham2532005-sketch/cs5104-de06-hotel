-- Q2 (bản viết ngây thơ, chỉ để so sánh N2/N3): kết nối thẳng trên khung nhìn all_*.
-- postgres_fdw KHÔNG đẩy được kết nối giữa hai khung nhìn UNION ALL -> kéo mọi dòng thoả WHERE về trạm trung tâm.
SELECT h.region, r.room_type_code, rt.name AS room_type,
       sum(b.nights * r.rate) AS revenue, count(*)::bigint AS bookings
FROM all_booking b
JOIN all_room r   ON r.room_id = b.room_id
JOIN all_hotel h  ON h.hotel_id = r.hotel_id
JOIN room_type rt ON rt.room_type_code = r.room_type_code
WHERE b.check_in >= DATE '2025-01-01' AND b.check_in < DATE '2026-01-01'
GROUP BY h.region, r.room_type_code, rt.name
ORDER BY h.region, r.room_type_code;
