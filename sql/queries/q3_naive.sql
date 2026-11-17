-- Q3 (bản ngây thơ trên all_*): điều kiện tour_group_id được đẩy xuống từng trạm,
-- nhưng kết nối với all_room/all_hotel làm ở trung tâm -> kéo thêm toàn bộ room và hotel về.
SELECT b.booking_id, b.check_in, b.nights, h.region, h.name AS hotel, r.room_id, r.room_type_code,
       b.guest_name, b.request ->> 'meal_plan' AS meal_plan
FROM all_booking b
JOIN all_room r  ON r.room_id = b.room_id
JOIN all_hotel h ON h.hotel_id = r.hotel_id
WHERE b.tour_group_id = 1
ORDER BY b.check_in, b.booking_id;
