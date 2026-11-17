-- Q5 trên CSDL đối chứng.
SELECT b.booking_id, b.guest_name, b.check_in
FROM public.booking b JOIN public.req_family f ON f.booking_id = b.booking_id
WHERE f.airport_pickup
  AND EXISTS (SELECT 1 FROM public.req_family_child c WHERE c.booking_id = f.booking_id AND c.age < 6)
ORDER BY booking_id;
