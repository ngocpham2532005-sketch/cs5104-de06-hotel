-- =====================================================================
-- site_schema.sql — LƯỢC ĐỒ MỘT TRẠM (dùng chung cho cả 4 trạm)
-- tools/load.py thay các tham số trước khi chạy:
--   __SITE__   tên vùng của trạm (dalat | nhatrang | phuquoc | danang)
--   __ID_LO__  __ID_HI__   dải booking_id dành cho dòng mới của trạm (no·10^7+1 .. (no+1)·10^7−1)
--
-- Không thêm/bớt/đổi tên bảng hay cột: mỗi mảnh giữ đúng tên bảng gốc.
-- Chỉ thêm: CHECK, chỉ mục, sequence (DEFAULT) — được đề cho phép.
--
-- Thiết kế:
--   room_type, tour_group : SAO CHÉP đầy đủ ra mọi trạm
--   hotel                 : NGANG CHÍNH  σ(region = '__SITE__')
--   room                  : NGANG DẪN XUẤT  room ⋉ hotel
--   booking               : NGANG DẪN XUẤT  booking ⋉ room   (vùng của khách sạn)
--   req_tour/business/family : DẪN XUẤT theo booking
--   req_family_child      : DẪN XUẤT nối tiếp theo req_family
-- Vì cha và con luôn cùng trạm, mọi khoá ngoại được khai báo THẬT tại trạm.
-- =====================================================================
DROP TABLE IF EXISTS req_family_child, req_family, req_business, req_tour,
                     booking, room, hotel, tour_group, room_type CASCADE;
DROP SEQUENCE IF EXISTS booking_id_seq, tour_group_id_seq;

-- ---------- bảng sao chép ----------
CREATE TABLE room_type (
    room_type_code text     PRIMARY KEY,
    name           text     NOT NULL,
    capacity       smallint NOT NULL
);

CREATE TABLE tour_group (
    tour_group_id  integer  PRIMARY KEY,
    agency         text     NOT NULL,
    size           smallint NOT NULL,
    start_date     date     NOT NULL
);

-- ---------- mảnh ngang chính ----------
CREATE TABLE hotel (
    hotel_id       integer  PRIMARY KEY,
    name           text     NOT NULL,
    region         text     NOT NULL,
    stars          smallint,
    CONSTRAINT hotel_fragment_chk CHECK (region = '__SITE__')   -- trạm chỉ nhận khách sạn của vùng mình
);

-- ---------- mảnh dẫn xuất ----------
CREATE TABLE room (
    room_id        integer  PRIMARY KEY,
    hotel_id       integer  NOT NULL REFERENCES hotel (hotel_id),          -- => phòng thuộc vùng của trạm
    room_type_code text     NOT NULL REFERENCES room_type (room_type_code),
    floor          smallint,
    rate           numeric  NOT NULL CHECK (rate > 0)
);

CREATE SEQUENCE booking_id_seq START __ID_LO__ MINVALUE __ID_LO__ MAXVALUE __ID_HI__;

CREATE TABLE booking (
    booking_id     integer  PRIMARY KEY DEFAULT nextval('booking_id_seq'),
    room_id        integer  NOT NULL REFERENCES room (room_id),            -- => lượt đặt thuộc vùng của trạm
    guest_name     text     NOT NULL,
    check_in       date     NOT NULL,
    nights         smallint NOT NULL CHECK (nights BETWEEN 1 AND 60),
    guest_type     text     NOT NULL,
    tour_group_id  integer  REFERENCES tour_group (tour_group_id),
    request        jsonb    NOT NULL,
    -- khoá chính duy nhất toàn hệ: dòng của bộ sinh (< 10^7) hoặc dòng mới trong dải của trạm
    CONSTRAINT booking_id_range_chk CHECK (booking_id < 10000000 OR booking_id BETWEEN __ID_LO__ AND __ID_HI__),
    -- CHECK cho cột loại jsonb
    CONSTRAINT booking_guest_type_chk CHECK (guest_type IN ('tour', 'business', 'family')),
    CONSTRAINT booking_tour_group_chk CHECK ((guest_type = 'tour') = (tour_group_id IS NOT NULL)),
    CONSTRAINT booking_request_shape_chk CHECK (
        jsonb_typeof(request) = 'object' AND
        CASE guest_type
          WHEN 'tour' THEN
                request ?& ARRAY['group_code', 'meal_plan', 'guide_room']
            AND request ->> 'meal_plan' IN ('BB', 'HB', 'FB')
            AND jsonb_typeof(request -> 'guide_room') = 'boolean'
            AND request ->> 'group_code' = 'TG' || CASE WHEN tour_group_id < 10000
                                                        THEN lpad(tour_group_id::text, 4, '0')
                                                        ELSE tour_group_id::text END
          WHEN 'business' THEN
                request ?& ARRAY['company', 'tax_code', 'late_checkout']
            AND jsonb_typeof(request -> 'late_checkout') = 'boolean'
          WHEN 'family' THEN
                request ?& ARRAY['extra_bed', 'children_ages', 'airport_pickup']
            AND jsonb_typeof(request -> 'extra_bed') = 'boolean'
            AND jsonb_typeof(request -> 'airport_pickup') = 'boolean'
            AND jsonb_typeof(request -> 'children_ages') = 'array'
          ELSE false
        END)
);
ALTER SEQUENCE booking_id_seq OWNED BY booking.booking_id;

CREATE TABLE req_tour (
    booking_id     integer  PRIMARY KEY REFERENCES booking (booking_id),
    group_code     text     NOT NULL,
    meal_plan      text     NOT NULL CHECK (meal_plan IN ('BB', 'HB', 'FB')),
    guide_room     boolean  NOT NULL
);

CREATE TABLE req_business (
    booking_id     integer  PRIMARY KEY REFERENCES booking (booking_id),
    company        text     NOT NULL,
    tax_code       text     NOT NULL,
    late_checkout  boolean  NOT NULL
);

CREATE TABLE req_family (
    booking_id     integer  PRIMARY KEY REFERENCES booking (booking_id),
    extra_bed      boolean  NOT NULL,
    airport_pickup boolean  NOT NULL
);

CREATE TABLE req_family_child (
    booking_id     integer  NOT NULL REFERENCES req_family (booking_id),
    seq            smallint NOT NULL,
    age            smallint NOT NULL CHECK (age BETWEEN 0 AND 17),
    PRIMARY KEY (booking_id, seq)
);

CREATE INDEX room_hotel_idx       ON room (hotel_id);
CREATE INDEX booking_room_idx     ON booking (room_id);
CREATE INDEX booking_tg_idx       ON booking (tour_group_id) WHERE tour_group_id IS NOT NULL;
CREATE INDEX booking_checkin_idx  ON booking (check_in);

-- ---------- khung nhìn cục bộ của trạm (được đề cho phép) ----------
-- Mục đích: để trạm trung tâm thấy kết nối booking⋈room⋈hotel của MỘT trạm như MỘT bảng ngoài.
-- Khi đó postgres_fdw đẩy được WHERE + GROUP BY xuống trạm mà không cần use_remote_estimate
-- (use_remote_estimate cũng đẩy được nhưng tốn thêm nhiều vòng khứ hồi EXPLAIN lúc lập kế hoạch — xem N3).
CREATE VIEW booking_detail AS
SELECT b.booking_id, b.room_id, b.guest_name, b.check_in, b.nights, b.guest_type, b.tour_group_id,
       r.room_type_code, r.rate, r.hotel_id, h.name AS hotel_name, h.region
FROM booking b
JOIN room r  ON r.room_id  = b.room_id
JOIN hotel h ON h.hotel_id = r.hotel_id;

-- Bản quan hệ của yêu cầu khách gia đình (req_family + req_family_child), kèm tên khách và ngày nhận phòng
CREATE VIEW family_request_detail AS
SELECT b.booking_id, b.guest_name, b.check_in, f.extra_bed, f.airport_pickup,
       (SELECT min(c.age)  FROM req_family_child c WHERE c.booking_id = f.booking_id) AS youngest_child_age,
       (SELECT count(*)    FROM req_family_child c WHERE c.booking_id = f.booking_id) AS children
FROM booking b
JOIN req_family f ON f.booking_id = b.booking_id;
