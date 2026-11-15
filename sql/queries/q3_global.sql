-- Q3 viết thẳng trên all_* (để so sánh với q3.sql)
SELECT b.booking_id, h.region, h.name AS hotel, b.room_id, r.room_type_code, b.check_in, b.nights, b.guest_name
FROM all_booking b
JOIN all_room r  ON r.room_id  = b.room_id
JOIN all_hotel h ON h.hotel_id = r.hotel_id
WHERE b.tour_group_id = :tg
ORDER BY b.check_in, b.booking_id;
