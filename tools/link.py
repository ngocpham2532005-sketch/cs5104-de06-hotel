"""
Nối các trạm vào trạm trung tâm bằng postgres_fdw (chạy lại được nhiều lần):
  - server srv_<trạm> trỏ tới IP:cổng của trạm (theo deploy.toml), user mapping;
  - schema s_<trạm> chứa foreign table của trạm đó (IMPORT FOREIGN SCHEMA);
    riêng trạm trung tâm: s_<trung tâm> là khung nhìn trên bảng cục bộ public.*;
  - CHECK (region = ...) khai báo trên foreign table hotel để planner loại nhánh (constraint exclusion);
  - khung nhìn toàn cục all_<bảng> = UNION ALL các mảnh, cho mỗi bảng bị chia;
  - schema ref: foreign table trỏ vào CSDL đối chứng hotel_ref (dùng cho make check).
"""
from cfg import CENTRAL, DB, REMOTE, SITES, ALL_TABLES, FRAGMENTED, connect, site, CFG

COLS = {
    "hotel": "hotel_id, name, region, stars",
    "room": "room_id, hotel_id, room_type_code, floor, rate",
    "booking": "booking_id, room_id, guest_name, check_in, nights, guest_type, tour_group_id, request",
    "req_tour": "booking_id, group_code, meal_plan, guide_room",
    "req_business": "booking_id, company, tax_code, late_checkout",
    "req_family": "booking_id, extra_bed, airport_pickup",
    "req_family_child": "booking_id, seq, age",
}


def server_sql(name, host, port, dbname):
    # use_remote_estimate=false: không gửi EXPLAIN sang trạm xa lúc lập kế hoạch (mỗi lần = 1 vòng khứ hồi);
    # fetch_size=1000: mỗi lần FETCH lấy 1000 dòng => ít vòng khứ hồi hơn mặc định 100
    pw = DB["password"].replace("'", "''")
    return f"""
DROP SERVER IF EXISTS srv_{name} CASCADE;
CREATE SERVER srv_{name} FOREIGN DATA WRAPPER postgres_fdw
  OPTIONS (host '{host}', port '{port}', dbname '{dbname}', connect_timeout '3',
           use_remote_estimate 'false', fetch_size '1000');
CREATE USER MAPPING FOR CURRENT_USER SERVER srv_{name}
  OPTIONS (user '{DB["user"]}', password '{pw}');
DROP SCHEMA IF EXISTS s_{name} CASCADE;
CREATE SCHEMA s_{name};
"""


VIEWS = ["v_revenue", "v_tour_room", "v_family_req"]   # khung nhìn mảnh tạo ở mỗi trạm (site_extra.sql)


def build_sql():
    tables = ", ".join(ALL_TABLES)
    tables_views = ", ".join(ALL_TABLES + VIEWS)
    out = ["CREATE EXTENSION IF NOT EXISTS postgres_fdw;"]
    for v in FRAGMENTED:
        out.append(f"DROP VIEW IF EXISTS all_{v} CASCADE;")
    for s in REMOTE:
        i = site(s)
        out.append(server_sql(s, i["ip"], i["port"], DB["dbname"]))
        out.append(f"IMPORT FOREIGN SCHEMA public LIMIT TO ({tables_views}) FROM SERVER srv_{s} INTO s_{s};")
        out.append(f"ALTER FOREIGN TABLE s_{s}.hotel ADD CONSTRAINT frag_hotel_region CHECK (region = '{s}');")
    # trạm trung tâm: mảnh của chính nó là bảng cục bộ
    out.append(f"DROP SCHEMA IF EXISTS s_{CENTRAL} CASCADE; CREATE SCHEMA s_{CENTRAL};")
    for t in ALL_TABLES + VIEWS:
        out.append(f"CREATE VIEW s_{CENTRAL}.{t} AS SELECT * FROM public.{t};")
    # khung nhìn toàn cục
    for t in FRAGMENTED:
        parts = "\n  UNION ALL ".join(f"SELECT {COLS[t]} FROM s_{s}.{t}" for s in SITES)
        out.append(f"CREATE VIEW all_{t} AS\n  {parts};")
    # CSDL đối chứng
    ref_host = CFG["db"].get("ref_fdw_host", "localhost")
    ref_port = CFG["db"].get("ref_fdw_port", 5432)
    out.append(server_sql("ref", ref_host, ref_port, DB["refdb"]).replace("s_ref", "ref"))
    out.append(f"IMPORT FOREIGN SCHEMA public LIMIT TO ({tables}) FROM SERVER srv_ref INTO ref;")
    return "\n".join(out)


def main():
    sql = build_sql()
    with connect(CENTRAL) as c:
        c.execute(sql)
        print(f"[link] trạm trung tâm {CENTRAL}: đã tạo srv_* cho {', '.join(REMOTE)} + ref, "
              f"khung nhìn all_{{{', '.join(FRAGMENTED)}}}")
        for s in SITES:
            try:
                n = c.scalar(f"SELECT count(*) FROM s_{s}.hotel")
                print(f"  s_{s:<9} OK  ({n} khách sạn)")
            except Exception as e:  # noqa: BLE001
                print(f"  s_{s:<9} LỖI {e}")
    (__import__("cfg").RESULTS / "link_generated.sql").write_text(sql, encoding="utf-8")


if __name__ == "__main__":
    main()
