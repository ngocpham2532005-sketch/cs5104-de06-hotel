-- =====================================================================
-- CS5104 · Đề 6 · Chuỗi khách sạn nghỉ dưỡng
-- schema_central.sql — LƯỢC ĐỒ TẬP TRUNG (đúng Hình 6.1), dùng cho CSDL đối chứng `ref`.
-- Tên bảng, cột, kiểu dữ liệu, khoá chính, khoá ngoại giữ nguyên theo đề.
-- =====================================================================
DROP TABLE IF EXISTS req_family_child, req_family, req_business, req_tour,
                     booking, room, hotel, tour_group, room_type CASCADE;

CREATE TABLE room_type (
    room_type_code text     PRIMARY KEY,          -- mã loại phòng
    name           text     NOT NULL,             -- tên
    capacity       smallint NOT NULL              -- sức chứa (người)
);

CREATE TABLE tour_group (
    tour_group_id  integer  PRIMARY KEY,          -- mã đoàn tour
    agency         text     NOT NULL,             -- công ty lữ hành
    size           smallint NOT NULL,             -- số người trong đoàn
    start_date     date     NOT NULL              -- ngày khởi hành
);

CREATE TABLE hotel (
    hotel_id       integer  PRIMARY KEY,          -- mã khách sạn
    name           text     NOT NULL,
    region         text     NOT NULL,             -- vùng: dalat | nhatrang | phuquoc | danang
    stars          smallint
);

CREATE TABLE room (
    room_id        integer  PRIMARY KEY,
    hotel_id       integer  NOT NULL REFERENCES hotel (hotel_id),
    room_type_code text     NOT NULL REFERENCES room_type (room_type_code),
    floor          smallint,
    rate           numeric  NOT NULL              -- giá phòng một đêm (đồng)
);

CREATE TABLE booking (
    booking_id     integer  PRIMARY KEY,
    room_id        integer  NOT NULL REFERENCES room (room_id),
    guest_name     text     NOT NULL,
    check_in       date     NOT NULL,
    nights         smallint NOT NULL,
    guest_type     text     NOT NULL,             -- tour | business | family
    tour_group_id  integer  REFERENCES tour_group (tour_group_id),  -- chỉ có khi guest_type = 'tour'
    request        jsonb    NOT NULL              -- yêu cầu, dạng theo guest_type
);

-- Bản quan hệ tương đương của booking.request (1 – 0..1 với booking)
CREATE TABLE req_tour (
    booking_id     integer  PRIMARY KEY REFERENCES booking (booking_id),
    group_code     text     NOT NULL,
    meal_plan      text     NOT NULL,             -- BB | HB | FB
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

CREATE TABLE req_family_child (                   -- mỗi phần tử children_ages[] một dòng
    booking_id     integer  NOT NULL REFERENCES req_family (booking_id),
    seq            smallint NOT NULL,
    age            smallint NOT NULL,
    PRIMARY KEY (booking_id, seq)
);

-- Chỉ mục giống các trạm, để so sánh thời gian công bằng
CREATE INDEX room_hotel_idx       ON room (hotel_id);
CREATE INDEX booking_room_idx     ON booking (room_id);
CREATE INDEX booking_tg_idx       ON booking (tour_group_id) WHERE tour_group_id IS NOT NULL;
CREATE INDEX booking_checkin_idx  ON booking (check_in);
