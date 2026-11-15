-- Q2 trên CSDL đối chứng
SELECT x.region, x.room_type_code, rt.name AS room_type,
       sum(x.bookings) AS bookings, sum(x.nights) AS nights, sum(x.revenue) AS revenue
FROM (
    SELECT h.region, r.room_type_code, count(*) AS bookings, sum(b.nights) AS nights,
           sum(b.nights * r.rate) AS revenue
    FROM booking b
    JOIN room r  ON r.room_id  = b.room_id
    JOIN hotel h ON h.hotel_id = r.hotel_id
    WHERE b.check_in >= DATE '2025-01-01' AND b.check_in < DATE '2026-01-01'
    GROUP BY h.region, r.room_type_code
) x
JOIN room_type rt ON rt.room_type_code = x.room_type_code
GROUP BY x.region, x.room_type_code, rt.name
ORDER BY x.region, x.room_type_code;
