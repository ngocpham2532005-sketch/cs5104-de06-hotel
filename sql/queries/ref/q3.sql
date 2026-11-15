-- Q3 trên CSDL đối chứng
SELECT b.booking_id, h.region, h.name AS hotel, b.room_id, r.room_type_code,
       b.check_in, b.nights, b.guest_name
FROM booking b
JOIN room r  ON r.room_id  = b.room_id
JOIN hotel h ON h.hotel_id = r.hotel_id
WHERE b.tour_group_id = :tg
ORDER BY check_in, booking_id;
