-- Q2 · Doanh thu (số đêm × giá phòng) theo vùng và loại phòng, lượt nhận phòng năm 2025 — gộp 4 trạm
-- Mỗi trạm tự JOIN + GROUP BY trong khung nhìn mảnh v_revenue; WHERE yr = 2025 được đẩy xuống trạm.
-- Trung tâm chỉ nhận vài chục dòng tổng con rồi gộp lần cuối và nối room_type (bảng sao chép, cục bộ).
SELECT x.region, x.room_type_code, rt.name AS room_type,
       sum(x.bookings) AS bookings, sum(x.nights) AS nights, sum(x.revenue) AS revenue
FROM (
  SELECT * FROM s_dalat.v_revenue WHERE yr = 2025
  UNION ALL SELECT * FROM s_nhatrang.v_revenue WHERE yr = 2025
  UNION ALL SELECT * FROM s_phuquoc.v_revenue WHERE yr = 2025
  UNION ALL SELECT * FROM s_danang.v_revenue WHERE yr = 2025
) x
JOIN room_type rt ON rt.room_type_code = x.room_type_code
GROUP BY x.region, x.room_type_code, rt.name
ORDER BY x.region, x.room_type_code;
