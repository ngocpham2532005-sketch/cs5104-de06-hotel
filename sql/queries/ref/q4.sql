-- Q4 trên CSDL đối chứng
SELECT b.booking_id, b.guest_name, b.check_in, b.nights
FROM booking b
WHERE b.guest_type = 'family'
  AND b.request @> '{"airport_pickup": true}'
  AND b.request @? '$.children_ages[*] ? (@ < 6)'
ORDER BY b.booking_id;
