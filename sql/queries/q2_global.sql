-- Q2 viết thẳng trên khung nhìn toàn cục all_* (để so sánh với q2.sql):
-- planner không ghép được JOIN qua UNION ALL => kéo booking năm 2025 của mọi trạm về trung tâm rồi mới JOIN.
SELECT h.region, r.room_type_code, rt.name AS room_type,
       count(*) AS bookings, sum(b.nights) AS nights, sum(b.nights * r.rate) AS revenue
FROM all_booking b
JOIN all_room r  ON r.room_id  = b.room_id
JOIN all_hotel h ON h.hotel_id = r.hotel_id
JOIN room_type rt ON rt.room_type_code = r.room_type_code
WHERE b.check_in >= DATE '2025-01-01' AND b.check_in < DATE '2026-01-01'
GROUP BY h.region, r.room_type_code, rt.name
ORDER BY h.region, r.room_type_code;
