-- Q3 · Toàn bộ phòng đã đặt của một đoàn tour đi qua nhiều vùng (đoàn TG0001), sắp theo ngày nhận phòng
-- Đoàn 1 luôn đi ≥ 2 vùng (bộ sinh ép). Booking chia theo vùng KHÁCH SẠN -> phòng của đoàn nằm ở nhiều trạm.
-- Không bảng nào cho biết đoàn đi những vùng nào -> không loại được trạm nào: hỏi cả 4 trạm (3 trạm xa).
-- Mỗi trạm tự lọc tour_group_id và kết nối booking⋈room⋈hotel (đẩy xuống); trung tâm chỉ UNION ALL + sắp xếp.
SELECT *
FROM (
    -- nhatrang (cục bộ)
    SELECT b.booking_id, b.check_in, b.nights, h.region, h.name AS hotel, r.room_id, r.room_type_code,
           b.guest_name, b.request ->> 'meal_plan' AS meal_plan
    FROM public.booking b JOIN public.room r ON r.room_id = b.room_id JOIN public.hotel h ON h.hotel_id = r.hotel_id
    WHERE b.tour_group_id = 1
    UNION ALL
    -- dalat
    SELECT b.booking_id, b.check_in, b.nights, h.region, h.name AS hotel, r.room_id, r.room_type_code,
           b.guest_name, b.request ->> 'meal_plan' AS meal_plan
    FROM s_dalat.booking b JOIN s_dalat.room r ON r.room_id = b.room_id JOIN s_dalat.hotel h ON h.hotel_id = r.hotel_id
    WHERE b.tour_group_id = 1
    UNION ALL
    -- phuquoc
    SELECT b.booking_id, b.check_in, b.nights, h.region, h.name AS hotel, r.room_id, r.room_type_code,
           b.guest_name, b.request ->> 'meal_plan' AS meal_plan
    FROM s_phuquoc.booking b JOIN s_phuquoc.room r ON r.room_id = b.room_id JOIN s_phuquoc.hotel h ON h.hotel_id = r.hotel_id
    WHERE b.tour_group_id = 1
    UNION ALL
    -- danang
    SELECT b.booking_id, b.check_in, b.nights, h.region, h.name AS hotel, r.room_id, r.room_type_code,
           b.guest_name, b.request ->> 'meal_plan' AS meal_plan
    FROM s_danang.booking b JOIN s_danang.room r ON r.room_id = b.room_id JOIN s_danang.hotel h ON h.hotel_id = r.hotel_id
    WHERE b.tour_group_id = 1
) x
ORDER BY check_in, booking_id;
