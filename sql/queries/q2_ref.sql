-- Q2 trên CSDL đối chứng (lược đồ tập trung).
SELECT h.region, r.room_type_code, rt.name AS room_type,
       sum(b.nights * r.rate) AS revenue, count(*)::bigint AS bookings
FROM booking b
JOIN room r   ON r.room_id = b.room_id
JOIN hotel h  ON h.hotel_id = r.hotel_id
JOIN room_type rt ON rt.room_type_code = r.room_type_code
WHERE b.check_in >= DATE '2025-01-01' AND b.check_in < DATE '2026-01-01'
GROUP BY h.region, r.room_type_code, rt.name
ORDER BY h.region, r.room_type_code;
