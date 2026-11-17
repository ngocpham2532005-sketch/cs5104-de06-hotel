-- Q3 (đoàn 3, một vùng) trên CSDL đối chứng.
SELECT b.booking_id, b.check_in, b.nights, h.region, h.name AS hotel, r.room_id, r.room_type_code,
       b.guest_name, b.request ->> 'meal_plan' AS meal_plan
FROM booking b
JOIN room r  ON r.room_id = b.room_id
JOIN hotel h ON h.hotel_id = r.hotel_id
WHERE b.tour_group_id = 3
ORDER BY b.check_in, b.booking_id;
