-- Q4 · Lượt đặt của khách gia đình có trẻ dưới 6 tuổi và cần đón sân bay — ĐỌC TỪ jsonb
-- Chạy ở trạm trung tâm trên booking: ba điều kiện (toán tử có sẵn @>, @?) được đẩy xuống từng trạm.
SELECT b.booking_id, b.guest_name, b.check_in
FROM booking b
WHERE b.guest_type = 'family'
  AND b.request @> '{"airport_pickup": true}'
  AND b.request @? '$.children_ages[*] ? (@ < 6)'
ORDER BY b.booking_id;
