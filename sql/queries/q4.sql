-- Q4 · Lượt đặt của khách gia đình có trẻ dưới 6 tuổi và cần đón sân bay — đọc từ jsonb
-- @> và @? là toán tử dựng sẵn, IMMUTABLE => được đẩy xuống từng trạm (xem Remote SQL)
SELECT b.booking_id, b.guest_name, b.check_in, b.nights
FROM all_booking b
WHERE b.guest_type = 'family'
  AND b.request @> '{"airport_pickup": true}'
  AND b.request @? '$.children_ages[*] ? (@ < 6)'
ORDER BY b.booking_id;
