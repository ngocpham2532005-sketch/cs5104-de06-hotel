-- Sinh tự động bởi tools/link.py từ deploy.toml
CREATE EXTENSION IF NOT EXISTS postgres_fdw;
DROP VIEW IF EXISTS all_hotel;
DROP VIEW IF EXISTS all_room;
DROP VIEW IF EXISTS all_booking;
DROP VIEW IF EXISTS all_req_tour;
DROP VIEW IF EXISTS all_req_business;
DROP VIEW IF EXISTS all_req_family;
DROP VIEW IF EXISTS all_req_family_child;
DROP SCHEMA IF EXISTS s_dalat CASCADE;
DROP SERVER IF EXISTS srv_dalat CASCADE;
CREATE SERVER srv_dalat FOREIGN DATA WRAPPER postgres_fdw OPTIONS (host 'dalat.db.nhom8.internal', port '5432', dbname 'hotel', connect_timeout '3', sslmode 'verify-full', sslrootcert '/var/lib/postgresql/18/docker/e3/ca.crt', sslnegotiation 'direct', fetch_size '10000', async_capable 'true', parallel_commit 'true');
CREATE USER MAPPING FOR postgres SERVER srv_dalat OPTIONS (user 'fdw_reader', sslcert '/var/lib/postgresql/18/docker/e3/fdw_reader.crt', sslkey '/var/lib/postgresql/18/docker/e3/fdw_reader.key');
CREATE SCHEMA s_dalat;
IMPORT FOREIGN SCHEMA public LIMIT TO (room_type, tour_group, hotel, room, booking, req_tour, req_business, req_family, req_family_child, booking_detail, family_request_detail) FROM SERVER srv_dalat INTO s_dalat;
DROP SCHEMA IF EXISTS s_phuquoc CASCADE;
DROP SERVER IF EXISTS srv_phuquoc CASCADE;
CREATE SERVER srv_phuquoc FOREIGN DATA WRAPPER postgres_fdw OPTIONS (host 'phuquoc.db.nhom8.internal', port '5435', dbname 'hotel', connect_timeout '3', sslmode 'verify-full', sslrootcert '/var/lib/postgresql/18/docker/e3/ca.crt', sslnegotiation 'direct', fetch_size '10000', async_capable 'true', parallel_commit 'true');
CREATE USER MAPPING FOR postgres SERVER srv_phuquoc OPTIONS (user 'fdw_reader', sslcert '/var/lib/postgresql/18/docker/e3/fdw_reader.crt', sslkey '/var/lib/postgresql/18/docker/e3/fdw_reader.key');
CREATE SCHEMA s_phuquoc;
IMPORT FOREIGN SCHEMA public LIMIT TO (room_type, tour_group, hotel, room, booking, req_tour, req_business, req_family, req_family_child, booking_detail, family_request_detail) FROM SERVER srv_phuquoc INTO s_phuquoc;
DROP SCHEMA IF EXISTS s_danang CASCADE;
DROP SERVER IF EXISTS srv_danang CASCADE;
CREATE SERVER srv_danang FOREIGN DATA WRAPPER postgres_fdw OPTIONS (host 'danang.db.nhom8.internal', port '5436', dbname 'hotel', connect_timeout '3', sslmode 'verify-full', sslrootcert '/var/lib/postgresql/18/docker/e3/ca.crt', sslnegotiation 'direct', fetch_size '10000', async_capable 'true', parallel_commit 'true');
CREATE USER MAPPING FOR postgres SERVER srv_danang OPTIONS (user 'fdw_reader', sslcert '/var/lib/postgresql/18/docker/e3/fdw_reader.crt', sslkey '/var/lib/postgresql/18/docker/e3/fdw_reader.key');
CREATE SCHEMA s_danang;
IMPORT FOREIGN SCHEMA public LIMIT TO (room_type, tour_group, hotel, room, booking, req_tour, req_business, req_family, req_family_child, booking_detail, family_request_detail) FROM SERVER srv_danang INTO s_danang;
DROP SCHEMA IF EXISTS ref CASCADE;
DROP SERVER IF EXISTS srv_ref CASCADE;
CREATE SERVER srv_ref FOREIGN DATA WRAPPER postgres_fdw OPTIONS (host 'ref.db.nhom8.internal', port '5432', dbname 'hotel', connect_timeout '3', sslmode 'verify-full', sslrootcert '/var/lib/postgresql/18/docker/e3/ca.crt', sslnegotiation 'direct', fetch_size '10000');
CREATE USER MAPPING FOR postgres SERVER srv_ref OPTIONS (user 'postgres', password 'cs5104');
CREATE SCHEMA ref;
IMPORT FOREIGN SCHEMA public LIMIT TO (room_type, tour_group, hotel, room, booking, req_tour, req_business, req_family, req_family_child) FROM SERVER srv_ref INTO ref;
CREATE VIEW all_hotel AS
    SELECT * FROM public.hotel
    UNION ALL SELECT * FROM s_dalat.hotel
    UNION ALL SELECT * FROM s_phuquoc.hotel
    UNION ALL SELECT * FROM s_danang.hotel;
COMMENT ON VIEW all_hotel IS 'Khung nhìn toàn cục: nhatrang (cục bộ) ∪ dalat ∪ phuquoc ∪ danang (postgres_fdw)';
CREATE VIEW all_room AS
    SELECT * FROM public.room
    UNION ALL SELECT * FROM s_dalat.room
    UNION ALL SELECT * FROM s_phuquoc.room
    UNION ALL SELECT * FROM s_danang.room;
COMMENT ON VIEW all_room IS 'Khung nhìn toàn cục: nhatrang (cục bộ) ∪ dalat ∪ phuquoc ∪ danang (postgres_fdw)';
CREATE VIEW all_booking AS
    SELECT * FROM public.booking
    UNION ALL SELECT * FROM s_dalat.booking
    UNION ALL SELECT * FROM s_phuquoc.booking
    UNION ALL SELECT * FROM s_danang.booking;
COMMENT ON VIEW all_booking IS 'Khung nhìn toàn cục: nhatrang (cục bộ) ∪ dalat ∪ phuquoc ∪ danang (postgres_fdw)';
CREATE VIEW all_req_tour AS
    SELECT * FROM public.req_tour
    UNION ALL SELECT * FROM s_dalat.req_tour
    UNION ALL SELECT * FROM s_phuquoc.req_tour
    UNION ALL SELECT * FROM s_danang.req_tour;
COMMENT ON VIEW all_req_tour IS 'Khung nhìn toàn cục: nhatrang (cục bộ) ∪ dalat ∪ phuquoc ∪ danang (postgres_fdw)';
CREATE VIEW all_req_business AS
    SELECT * FROM public.req_business
    UNION ALL SELECT * FROM s_dalat.req_business
    UNION ALL SELECT * FROM s_phuquoc.req_business
    UNION ALL SELECT * FROM s_danang.req_business;
COMMENT ON VIEW all_req_business IS 'Khung nhìn toàn cục: nhatrang (cục bộ) ∪ dalat ∪ phuquoc ∪ danang (postgres_fdw)';
CREATE VIEW all_req_family AS
    SELECT * FROM public.req_family
    UNION ALL SELECT * FROM s_dalat.req_family
    UNION ALL SELECT * FROM s_phuquoc.req_family
    UNION ALL SELECT * FROM s_danang.req_family;
COMMENT ON VIEW all_req_family IS 'Khung nhìn toàn cục: nhatrang (cục bộ) ∪ dalat ∪ phuquoc ∪ danang (postgres_fdw)';
CREATE VIEW all_req_family_child AS
    SELECT * FROM public.req_family_child
    UNION ALL SELECT * FROM s_dalat.req_family_child
    UNION ALL SELECT * FROM s_phuquoc.req_family_child
    UNION ALL SELECT * FROM s_danang.req_family_child;
COMMENT ON VIEW all_req_family_child IS 'Khung nhìn toàn cục: nhatrang (cục bộ) ∪ dalat ∪ phuquoc ∪ danang (postgres_fdw)';
