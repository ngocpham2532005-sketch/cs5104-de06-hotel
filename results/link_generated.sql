CREATE EXTENSION IF NOT EXISTS postgres_fdw;
DROP VIEW IF EXISTS all_hotel CASCADE;
DROP VIEW IF EXISTS all_room CASCADE;
DROP VIEW IF EXISTS all_booking CASCADE;
DROP VIEW IF EXISTS all_req_tour CASCADE;
DROP VIEW IF EXISTS all_req_business CASCADE;
DROP VIEW IF EXISTS all_req_family CASCADE;
DROP VIEW IF EXISTS all_req_family_child CASCADE;

DROP SERVER IF EXISTS srv_dalat CASCADE;
CREATE SERVER srv_dalat FOREIGN DATA WRAPPER postgres_fdw
  OPTIONS (host '172.16.105.6', port '5434', dbname 'hotel', connect_timeout '3',
           use_remote_estimate 'false', fetch_size '1000');
CREATE USER MAPPING FOR CURRENT_USER SERVER srv_dalat
  OPTIONS (user 'postgres', password 'cs5104');
DROP SCHEMA IF EXISTS s_dalat CASCADE;
CREATE SCHEMA s_dalat;

IMPORT FOREIGN SCHEMA public LIMIT TO (room_type, tour_group, hotel, room, booking, req_tour, req_business, req_family, req_family_child, v_revenue, v_tour_room, v_family_req) FROM SERVER srv_dalat INTO s_dalat;
ALTER FOREIGN TABLE s_dalat.hotel ADD CONSTRAINT frag_hotel_region CHECK (region = 'dalat');

DROP SERVER IF EXISTS srv_phuquoc CASCADE;
CREATE SERVER srv_phuquoc FOREIGN DATA WRAPPER postgres_fdw
  OPTIONS (host '172.16.105.6', port '5435', dbname 'hotel', connect_timeout '3',
           use_remote_estimate 'false', fetch_size '1000');
CREATE USER MAPPING FOR CURRENT_USER SERVER srv_phuquoc
  OPTIONS (user 'postgres', password 'cs5104');
DROP SCHEMA IF EXISTS s_phuquoc CASCADE;
CREATE SCHEMA s_phuquoc;

IMPORT FOREIGN SCHEMA public LIMIT TO (room_type, tour_group, hotel, room, booking, req_tour, req_business, req_family, req_family_child, v_revenue, v_tour_room, v_family_req) FROM SERVER srv_phuquoc INTO s_phuquoc;
ALTER FOREIGN TABLE s_phuquoc.hotel ADD CONSTRAINT frag_hotel_region CHECK (region = 'phuquoc');

DROP SERVER IF EXISTS srv_danang CASCADE;
CREATE SERVER srv_danang FOREIGN DATA WRAPPER postgres_fdw
  OPTIONS (host '172.16.105.6', port '5436', dbname 'hotel', connect_timeout '3',
           use_remote_estimate 'false', fetch_size '1000');
CREATE USER MAPPING FOR CURRENT_USER SERVER srv_danang
  OPTIONS (user 'postgres', password 'cs5104');
DROP SCHEMA IF EXISTS s_danang CASCADE;
CREATE SCHEMA s_danang;

IMPORT FOREIGN SCHEMA public LIMIT TO (room_type, tour_group, hotel, room, booking, req_tour, req_business, req_family, req_family_child, v_revenue, v_tour_room, v_family_req) FROM SERVER srv_danang INTO s_danang;
ALTER FOREIGN TABLE s_danang.hotel ADD CONSTRAINT frag_hotel_region CHECK (region = 'danang');
DROP SCHEMA IF EXISTS s_nhatrang CASCADE; CREATE SCHEMA s_nhatrang;
CREATE VIEW s_nhatrang.room_type AS SELECT * FROM public.room_type;
CREATE VIEW s_nhatrang.tour_group AS SELECT * FROM public.tour_group;
CREATE VIEW s_nhatrang.hotel AS SELECT * FROM public.hotel;
CREATE VIEW s_nhatrang.room AS SELECT * FROM public.room;
CREATE VIEW s_nhatrang.booking AS SELECT * FROM public.booking;
CREATE VIEW s_nhatrang.req_tour AS SELECT * FROM public.req_tour;
CREATE VIEW s_nhatrang.req_business AS SELECT * FROM public.req_business;
CREATE VIEW s_nhatrang.req_family AS SELECT * FROM public.req_family;
CREATE VIEW s_nhatrang.req_family_child AS SELECT * FROM public.req_family_child;
CREATE VIEW s_nhatrang.v_revenue AS SELECT * FROM public.v_revenue;
CREATE VIEW s_nhatrang.v_tour_room AS SELECT * FROM public.v_tour_room;
CREATE VIEW s_nhatrang.v_family_req AS SELECT * FROM public.v_family_req;
CREATE VIEW all_hotel AS
  SELECT hotel_id, name, region, stars FROM s_dalat.hotel
  UNION ALL SELECT hotel_id, name, region, stars FROM s_nhatrang.hotel
  UNION ALL SELECT hotel_id, name, region, stars FROM s_phuquoc.hotel
  UNION ALL SELECT hotel_id, name, region, stars FROM s_danang.hotel;
CREATE VIEW all_room AS
  SELECT room_id, hotel_id, room_type_code, floor, rate FROM s_dalat.room
  UNION ALL SELECT room_id, hotel_id, room_type_code, floor, rate FROM s_nhatrang.room
  UNION ALL SELECT room_id, hotel_id, room_type_code, floor, rate FROM s_phuquoc.room
  UNION ALL SELECT room_id, hotel_id, room_type_code, floor, rate FROM s_danang.room;
CREATE VIEW all_booking AS
  SELECT booking_id, room_id, guest_name, check_in, nights, guest_type, tour_group_id, request FROM s_dalat.booking
  UNION ALL SELECT booking_id, room_id, guest_name, check_in, nights, guest_type, tour_group_id, request FROM s_nhatrang.booking
  UNION ALL SELECT booking_id, room_id, guest_name, check_in, nights, guest_type, tour_group_id, request FROM s_phuquoc.booking
  UNION ALL SELECT booking_id, room_id, guest_name, check_in, nights, guest_type, tour_group_id, request FROM s_danang.booking;
CREATE VIEW all_req_tour AS
  SELECT booking_id, group_code, meal_plan, guide_room FROM s_dalat.req_tour
  UNION ALL SELECT booking_id, group_code, meal_plan, guide_room FROM s_nhatrang.req_tour
  UNION ALL SELECT booking_id, group_code, meal_plan, guide_room FROM s_phuquoc.req_tour
  UNION ALL SELECT booking_id, group_code, meal_plan, guide_room FROM s_danang.req_tour;
CREATE VIEW all_req_business AS
  SELECT booking_id, company, tax_code, late_checkout FROM s_dalat.req_business
  UNION ALL SELECT booking_id, company, tax_code, late_checkout FROM s_nhatrang.req_business
  UNION ALL SELECT booking_id, company, tax_code, late_checkout FROM s_phuquoc.req_business
  UNION ALL SELECT booking_id, company, tax_code, late_checkout FROM s_danang.req_business;
CREATE VIEW all_req_family AS
  SELECT booking_id, extra_bed, airport_pickup FROM s_dalat.req_family
  UNION ALL SELECT booking_id, extra_bed, airport_pickup FROM s_nhatrang.req_family
  UNION ALL SELECT booking_id, extra_bed, airport_pickup FROM s_phuquoc.req_family
  UNION ALL SELECT booking_id, extra_bed, airport_pickup FROM s_danang.req_family;
CREATE VIEW all_req_family_child AS
  SELECT booking_id, seq, age FROM s_dalat.req_family_child
  UNION ALL SELECT booking_id, seq, age FROM s_nhatrang.req_family_child
  UNION ALL SELECT booking_id, seq, age FROM s_phuquoc.req_family_child
  UNION ALL SELECT booking_id, seq, age FROM s_danang.req_family_child;

DROP SERVER IF EXISTS srv_ref CASCADE;
CREATE SERVER srv_ref FOREIGN DATA WRAPPER postgres_fdw
  OPTIONS (host 'localhost', port '5432', dbname 'hotel_ref', connect_timeout '3',
           use_remote_estimate 'false', fetch_size '1000');
CREATE USER MAPPING FOR CURRENT_USER SERVER srv_ref
  OPTIONS (user 'postgres', password 'cs5104');
DROP SCHEMA IF EXISTS ref CASCADE;
CREATE SCHEMA ref;

IMPORT FOREIGN SCHEMA public LIMIT TO (room_type, tour_group, hotel, room, booking, req_tour, req_business, req_family, req_family_child) FROM SERVER srv_ref INTO ref;