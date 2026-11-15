-- Q5 trên CSDL đối chứng
SELECT b.booking_id, b.guest_name, b.check_in, b.nights
FROM booking b
JOIN req_family f       ON f.booking_id = b.booking_id
JOIN req_family_child c ON c.booking_id = b.booking_id
WHERE f.airport_pickup AND c.age < 6
GROUP BY b.booking_id, b.guest_name, b.check_in, b.nights
ORDER BY booking_id;
