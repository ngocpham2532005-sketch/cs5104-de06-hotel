-- Q5 (biến thể so sánh): kết nối booking, req_family, req_family_child (bảng ngoài) của từng trạm.
-- Không bật use_remote_estimate, bộ tối ưu kéo cả ba bảng về rồi mới kết nối.
SELECT *
FROM (
    -- nhatrang (cục bộ)
    SELECT b.booking_id, b.guest_name, b.check_in
    FROM public.booking b JOIN public.req_family f ON f.booking_id = b.booking_id
    WHERE f.airport_pickup
      AND EXISTS (SELECT 1 FROM public.req_family_child c WHERE c.booking_id = f.booking_id AND c.age < 6)
    UNION ALL
    -- dalat
    SELECT b.booking_id, b.guest_name, b.check_in
    FROM s_dalat.booking b JOIN s_dalat.req_family f ON f.booking_id = b.booking_id
    WHERE f.airport_pickup
      AND EXISTS (SELECT 1 FROM s_dalat.req_family_child c WHERE c.booking_id = f.booking_id AND c.age < 6)
    UNION ALL
    -- phuquoc
    SELECT b.booking_id, b.guest_name, b.check_in
    FROM s_phuquoc.booking b JOIN s_phuquoc.req_family f ON f.booking_id = b.booking_id
    WHERE f.airport_pickup
      AND EXISTS (SELECT 1 FROM s_phuquoc.req_family_child c WHERE c.booking_id = f.booking_id AND c.age < 6)
    UNION ALL
    -- danang
    SELECT b.booking_id, b.guest_name, b.check_in
    FROM s_danang.booking b JOIN s_danang.req_family f ON f.booking_id = b.booking_id
    WHERE f.airport_pickup
      AND EXISTS (SELECT 1 FROM s_danang.req_family_child c WHERE c.booking_id = f.booking_id AND c.age < 6)
) x
ORDER BY booking_id;
