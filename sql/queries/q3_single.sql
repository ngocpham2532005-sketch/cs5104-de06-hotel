-- Q3 cho đoàn CHỈ ĐI MỘT VÙNG (đoàn TG0003: 45 phòng, tất cả ở danang) — dùng để so với q3.sql (đoàn 1, 3 vùng) ở N4.
-- Câu hỏi giống hệt Q3, chỉ đổi mã đoàn: trạm trung tâm không biết trước đoàn đi đâu nên vẫn hỏi cả 4 trạm.
SELECT *
FROM (
    -- nhatrang (cục bộ)
    SELECT b.booking_id, b.check_in, b.nights, h.region, h.name AS hotel, r.room_id, r.room_type_code,
           b.guest_name, b.request ->> 'meal_plan' AS meal_plan
    FROM public.booking b JOIN public.room r ON r.room_id = b.room_id JOIN public.hotel h ON h.hotel_id = r.hotel_id
    WHERE b.tour_group_id = 3
    UNION ALL
    -- dalat
    SELECT b.booking_id, b.check_in, b.nights, h.region, h.name AS hotel, r.room_id, r.room_type_code,
           b.guest_name, b.request ->> 'meal_plan' AS meal_plan
    FROM s_dalat.booking b JOIN s_dalat.room r ON r.room_id = b.room_id JOIN s_dalat.hotel h ON h.hotel_id = r.hotel_id
    WHERE b.tour_group_id = 3
    UNION ALL
    -- phuquoc
    SELECT b.booking_id, b.check_in, b.nights, h.region, h.name AS hotel, r.room_id, r.room_type_code,
           b.guest_name, b.request ->> 'meal_plan' AS meal_plan
    FROM s_phuquoc.booking b JOIN s_phuquoc.room r ON r.room_id = b.room_id JOIN s_phuquoc.hotel h ON h.hotel_id = r.hotel_id
    WHERE b.tour_group_id = 3
    UNION ALL
    -- danang
    SELECT b.booking_id, b.check_in, b.nights, h.region, h.name AS hotel, r.room_id, r.room_type_code,
           b.guest_name, b.request ->> 'meal_plan' AS meal_plan
    FROM s_danang.booking b JOIN s_danang.room r ON r.room_id = b.room_id JOIN s_danang.hotel h ON h.hotel_id = r.hotel_id
    WHERE b.tour_group_id = 3
) x
ORDER BY check_in, booking_id;
