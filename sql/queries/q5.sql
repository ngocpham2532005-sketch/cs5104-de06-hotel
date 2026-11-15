-- Q5 · Như Q4 nhưng đọc từ bản quan hệ req_family + req_family_child
-- Khung nhìn mảnh v_family_req (JOIN booking–req_family, tuổi nhỏ nhất của trẻ) chạy tại từng trạm.
SELECT booking_id, guest_name, check_in, nights
FROM (
  SELECT booking_id, guest_name, check_in, nights FROM s_dalat.v_family_req WHERE airport_pickup AND min_child_age < 6
  UNION ALL SELECT booking_id, guest_name, check_in, nights FROM s_nhatrang.v_family_req WHERE airport_pickup AND min_child_age < 6
  UNION ALL SELECT booking_id, guest_name, check_in, nights FROM s_phuquoc.v_family_req WHERE airport_pickup AND min_child_age < 6
  UNION ALL SELECT booking_id, guest_name, check_in, nights FROM s_danang.v_family_req WHERE airport_pickup AND min_child_age < 6
) x
ORDER BY booking_id;
