-- =====================================================================
-- CS5104 · Đề 6 — Chuỗi khách sạn nghỉ dưỡng
-- Lược đồ TẬP TRUNG (Hình 6.1) — dùng cho CSDL đối chứng hotel_ref.
-- Không thêm/bớt/đổi tên bảng, cột. Chỉ thêm CHECK, chỉ mục.
-- Nạp: bảng cha trước, bảng con sau (room_type, tour_group, hotel, room,
--      booking, req_tour, req_business, req_family, req_family_child).
-- =====================================================================

CREATE TABLE room_type (
    room_type_code  text      PRIMARY KEY,
    name            text      NOT NULL,
    capacity        smallint  NOT NULL CHECK (capacity > 0)
);

CREATE TABLE tour_group (
    tour_group_id   integer   PRIMARY KEY,
    agency          text      NOT NULL,
    size            smallint  NOT NULL CHECK (size > 0),
    start_date      date      NOT NULL
);

CREATE TABLE hotel (
    hotel_id        integer   PRIMARY KEY,
    name            text      NOT NULL,
    region          text      NOT NULL CHECK (region IN ('dalat','nhatrang','phuquoc','danang')),
    stars           smallint  NOT NULL CHECK (stars BETWEEN 1 AND 5)
);

CREATE TABLE room (
    room_id         integer   PRIMARY KEY,
    hotel_id        integer   NOT NULL REFERENCES hotel(hotel_id),
    room_type_code  text      NOT NULL REFERENCES room_type(room_type_code),
    floor           smallint  NOT NULL,
    rate            numeric   NOT NULL CHECK (rate >= 0)
);

CREATE TABLE booking (
    booking_id      integer   PRIMARY KEY,
    room_id         integer   NOT NULL REFERENCES room(room_id),
    guest_name      text      NOT NULL,
    check_in        date      NOT NULL,
    nights          smallint  NOT NULL CHECK (nights > 0),
    guest_type      text      NOT NULL CHECK (guest_type IN ('tour','business','family')),
    tour_group_id   integer   REFERENCES tour_group(tour_group_id),
    request         jsonb     NOT NULL,
    -- CHECK cho cột jsonb: mỗi guest_type một dạng (Hình 6.2); tour_group_id chỉ có khi tour
    CONSTRAINT booking_request_shape CHECK (
        jsonb_typeof(request) = 'object' AND
        CASE guest_type
          WHEN 'tour' THEN
               tour_group_id IS NOT NULL
           AND request ?& ARRAY['group_code','meal_plan','guide_room']
           AND request->>'meal_plan' IN ('BB','HB','FB')
           AND jsonb_typeof(request->'guide_room') = 'boolean'
           AND request->>'group_code' = 'TG' || lpad(tour_group_id::text, greatest(4, length(tour_group_id::text)), '0')
          WHEN 'business' THEN
               tour_group_id IS NULL
           AND request ?& ARRAY['company','tax_code','late_checkout']
           AND jsonb_typeof(request->'late_checkout') = 'boolean'
          WHEN 'family' THEN
               tour_group_id IS NULL
           AND request ?& ARRAY['extra_bed','children_ages','airport_pickup']
           AND jsonb_typeof(request->'extra_bed') = 'boolean'
           AND jsonb_typeof(request->'airport_pickup') = 'boolean'
           AND jsonb_typeof(request->'children_ages') = 'array'
           AND NOT jsonb_path_exists(request, 'strict $.children_ages[*] ? (@.type() != "number")')
          ELSE false
        END)
);

-- Bản quan hệ tương đương của booking.request (nối 1 – 0..1 với booking)
CREATE TABLE req_tour (
    booking_id      integer   PRIMARY KEY REFERENCES booking(booking_id),
    group_code      text      NOT NULL,
    meal_plan       text      NOT NULL CHECK (meal_plan IN ('BB','HB','FB')),
    guide_room      boolean   NOT NULL
);

CREATE TABLE req_business (
    booking_id      integer   PRIMARY KEY REFERENCES booking(booking_id),
    company         text      NOT NULL,
    tax_code        text      NOT NULL,
    late_checkout   boolean   NOT NULL
);

CREATE TABLE req_family (
    booking_id      integer   PRIMARY KEY REFERENCES booking(booking_id),
    extra_bed       boolean   NOT NULL,
    airport_pickup  boolean   NOT NULL
);

CREATE TABLE req_family_child (
    booking_id      integer   NOT NULL REFERENCES req_family(booking_id),
    seq             smallint  NOT NULL CHECK (seq >= 1),
    age             smallint  NOT NULL CHECK (age BETWEEN 0 AND 17),
    PRIMARY KEY (booking_id, seq)
);

-- Chỉ mục phục vụ Q1–Q5 (giống hệt ở mỗi trạm để so sánh công bằng)
CREATE INDEX room_hotel_idx      ON room(hotel_id);
CREATE INDEX booking_room_idx    ON booking(room_id);
CREATE INDEX booking_checkin_idx ON booking(check_in);
CREATE INDEX booking_tg_idx      ON booking(tour_group_id);
