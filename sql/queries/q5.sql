-- Q5 · Như Q4 nhưng đọc từ bản quan hệ req_family + req_family_child
-- family_request_detail là khung nhìn cục bộ ở mỗi trạm trên booking ⋈ req_family, kèm tuổi nhỏ nhất
-- trong req_family_child (youngest_child_age < 6  ⇔  EXISTS một trẻ dưới 6 tuổi).
-- Mỗi trạm tự lọc (WHERE đẩy xuống, hỏi song song); trung tâm chỉ UNION ALL + sắp xếp.
SELECT *
FROM (
    -- nhatrang (cục bộ)
    SELECT booking_id, guest_name, check_in
    FROM public.family_request_detail
    WHERE airport_pickup AND youngest_child_age < 6
    UNION ALL
    -- dalat
    SELECT booking_id, guest_name, check_in
    FROM s_dalat.family_request_detail
    WHERE airport_pickup AND youngest_child_age < 6
    UNION ALL
    -- phuquoc
    SELECT booking_id, guest_name, check_in
    FROM s_phuquoc.family_request_detail
    WHERE airport_pickup AND youngest_child_age < 6
    UNION ALL
    -- danang
    SELECT booking_id, guest_name, check_in
    FROM s_danang.family_request_detail
    WHERE airport_pickup AND youngest_child_age < 6
) x
ORDER BY booking_id;
