-- Q3 · Toàn bộ phòng đã đặt của một đoàn tour đi qua nhiều vùng, sắp theo ngày nhận phòng
-- :tg = mã đoàn (mặc định 410: có phòng ở dalat, phuquoc, danang). Trong psql: \set tg 410
-- tour_group được sao chép nhưng booking chia theo vùng KHÁCH SẠN, trung tâm không biết trước đoàn
-- có phòng ở vùng nào => hỏi cả 4 trạm; WHERE tour_group_id = :tg được đẩy xuống từng trạm.
SELECT booking_id, region, hotel, room_id, room_type_code, check_in, nights, guest_name
FROM (
  SELECT booking_id, region, hotel, room_id, room_type_code, check_in, nights, guest_name FROM s_dalat.v_tour_room WHERE tour_group_id = :tg
  UNION ALL SELECT booking_id, region, hotel, room_id, room_type_code, check_in, nights, guest_name FROM s_nhatrang.v_tour_room WHERE tour_group_id = :tg
  UNION ALL SELECT booking_id, region, hotel, room_id, room_type_code, check_in, nights, guest_name FROM s_phuquoc.v_tour_room WHERE tour_group_id = :tg
  UNION ALL SELECT booking_id, region, hotel, room_id, room_type_code, check_in, nights, guest_name FROM s_danang.v_tour_room WHERE tour_group_id = :tg
) x
ORDER BY check_in, booking_id;
