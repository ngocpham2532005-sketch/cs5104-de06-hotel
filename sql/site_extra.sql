-- =====================================================================
-- Phần THÊM cho mỗi trạm (chạy SAU schema_central.sql trên CSDL của trạm).
-- {{REGION}} và {{SITE_NO}} được tools/load.py thay theo deploy.toml.
-- Mọi khoá ngoại của lược đồ đều ở cùng trạm với bảng cha (xem báo cáo),
-- nên giữ nguyên REFERENCES của schema_central.sql.
-- =====================================================================

-- 1) Ràng buộc mảnh — mảnh ngang chính: hotel_{{REGION}} = σ(region = '{{REGION}}') hotel
ALTER TABLE hotel ADD CONSTRAINT frag_hotel_region CHECK (region = '{{REGION}}');
--    Mảnh ngang dẫn xuất room ⋉ hotel, booking ⋉ room, req_* ⋉ booking:
--    không viết được bằng CHECK (cần nhìn bảng khác) — được bảo đảm bởi KHOÁ NGOẠI CỤC BỘ:
--    room.hotel_id phải tồn tại trong hotel CỦA TRẠM NÀY, mà hotel ở đây chỉ có region='{{REGION}}'.
--    Tương tự booking.room_id -> room cục bộ, req_* -> booking cục bộ.

-- 2) Khoá chính duy nhất toàn hệ khi mỗi trạm tự thêm dòng:
--    dữ liệu gốc dùng 1..999999; dòng mới = 1.000.000 + 10*n + site_no (chữ số cuối = trạm).
CREATE SEQUENCE hotel_id_seq   START 100000{{SITE_NO}} INCREMENT 10;
CREATE SEQUENCE room_id_seq    START 100000{{SITE_NO}} INCREMENT 10;
CREATE SEQUENCE booking_id_seq START 100000{{SITE_NO}} INCREMENT 10;
ALTER TABLE hotel   ALTER COLUMN hotel_id   SET DEFAULT nextval('hotel_id_seq');
ALTER TABLE room    ALTER COLUMN room_id    SET DEFAULT nextval('room_id_seq');
ALTER TABLE booking ALTER COLUMN booking_id SET DEFAULT nextval('booking_id_seq');
ALTER TABLE hotel   ADD CONSTRAINT pk_range_hotel   CHECK (hotel_id   < 1000000 OR hotel_id   % 10 = {{SITE_NO}});
ALTER TABLE room    ADD CONSTRAINT pk_range_room    CHECK (room_id    < 1000000 OR room_id    % 10 = {{SITE_NO}});
ALTER TABLE booking ADD CONSTRAINT pk_range_booking CHECK (booking_id < 1000000 OR booking_id % 10 = {{SITE_NO}});
--    tour_group là bảng SAO CHÉP: chỉ trạm trung tâm cấp mã (đuôi 0), ghi ra mọi trạm bằng 2PC.
ALTER TABLE tour_group ADD CONSTRAINT pk_range_tour_group CHECK (tour_group_id < 1000000 OR tour_group_id % 10 = 0);

COMMENT ON DATABASE {{DBNAME}} IS 'CS5104 De 6 - tram {{REGION}} (site_no {{SITE_NO}})';

-- 3) Khung nhìn mảnh (chạy tại trạm, trên dữ liệu cục bộ). Trạm trung tâm IMPORT chúng như
--    foreign table: mỗi trạm chỉ nhận MỘT câu SELECT đơn giản, điều kiện WHERE được đẩy xuống,
--    JOIN/GROUP BY làm tại trạm — không cần use_remote_estimate (vốn tốn nhiều vòng EXPLAIN).
CREATE VIEW v_revenue AS            -- Q2: doanh thu theo vùng × loại phòng × năm nhận phòng
SELECT h.region, r.room_type_code, extract(year FROM b.check_in)::int AS yr,
       count(*) AS bookings, sum(b.nights) AS nights, sum(b.nights * r.rate) AS revenue
FROM booking b JOIN room r ON r.room_id = b.room_id JOIN hotel h ON h.hotel_id = r.hotel_id
GROUP BY h.region, r.room_type_code, extract(year FROM b.check_in)::int;

CREATE VIEW v_tour_room AS          -- Q3: phòng đã đặt của các đoàn tour (lọc tour_group_id tại trạm)
SELECT b.booking_id, b.tour_group_id, h.region, h.name AS hotel, b.room_id, r.room_type_code,
       b.check_in, b.nights, b.guest_name
FROM booking b JOIN room r ON r.room_id = b.room_id JOIN hotel h ON h.hotel_id = r.hotel_id
WHERE b.tour_group_id IS NOT NULL;

CREATE VIEW v_family_req AS         -- Q5: khách gia đình đọc từ bản quan hệ (tuổi nhỏ nhất của trẻ)
SELECT b.booking_id, b.guest_name, b.check_in, b.nights, f.extra_bed, f.airport_pickup,
       (SELECT min(c.age) FROM req_family_child c WHERE c.booking_id = b.booking_id) AS min_child_age
FROM booking b JOIN req_family f ON f.booking_id = b.booking_id;
