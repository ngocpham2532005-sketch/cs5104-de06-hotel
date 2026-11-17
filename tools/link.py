#!/usr/bin/env python3
"""Ở trạm trung tâm: postgres_fdw tới 3 trạm còn lại + CSDL đối chứng, và khung nhìn toàn cục all_<bảng>.

    python tools/link.py
Kết quả ở trạm trung tâm (nhatrang):
  schema s_dalat, s_phuquoc, s_danang : bảng ngoài trỏ tới mảnh ở trạm xa (IMPORT FOREIGN SCHEMA)
  schema ref                         : bảng ngoài trỏ tới CSDL đối chứng (để make check so sánh bằng SQL)
  public.all_<bảng>                  : UNION ALL mảnh cục bộ + mảnh ở 3 trạm xa (7 bảng bị chia)
SQL sinh ra được ghi lại vào sql/generated_link.sql để đọc/đưa vào báo cáo.

E3 (mặc định): mọi srv_* gọi nút bằng TÊN <nút>.<domain> (DNS nội bộ ở trạm trung tâm), sslmode=verify-full,
sslnegotiation=direct; trạm xa: user fdw_reader + chứng chỉ máy khách, KHÔNG mật khẩu (pg_hba `cert`, chỉ SELECT);
ref: postgres + mật khẩu qua TLS. `make tls-off` => như cũ (IP/tên container, không mã hoá).
"""
from common import ALL_TABLES, FRAGMENTED, ROOT, Config
from tls_site import ROLE, SUBDIR

SITE_VIEWS = ["booking_detail", "family_request_detail"]   # khung nhìn cục bộ ở mỗi trạm (site_schema.sql)


def build_sql(cfg: Config, cdir: str | None = None) -> str:
    """cdir: thư mục chứng chỉ (ca.crt, fdw_reader.*) trong container trạm trung tâm; None => không TLS."""
    lines = ["-- Sinh tự động bởi tools/link.py từ " + cfg.path.name,
             "CREATE EXTENSION IF NOT EXISTS postgres_fdw;"]
    for t in FRAGMENTED:
        lines.append(f"DROP VIEW IF EXISTS all_{t};")
    targets = cfg.remote_sites() + ["ref"]
    for n in targets:
        host, port = cfg.docker_addr(n)
        srv = f"srv_{n}"
        schema = "ref" if n == "ref" else f"s_{n}"
        if cdir:
            host = cfg.fqdn(n)
        opts = [f"host '{host}'", f"port '{port}'", f"dbname '{cfg.db}'", "connect_timeout '3'"]
        if cdir:
            opts += ["sslmode 'verify-full'", f"sslrootcert '{cdir}/ca.crt'", "sslnegotiation 'direct'"]
        if n != "ref":
            # Ch.3 §3.4.4: lô lớn -> ít vòng khứ hồi; hỏi song song các trạm xa
            # parallel_commit: COMMIT tới các trạm xa gửi song song thay vì lần lượt (PG ≥ 15)
            opts += ["fetch_size '10000'", "async_capable 'true'", "parallel_commit 'true'"]
        else:
            opts += ["fetch_size '10000'"]
        imported = ALL_TABLES + ([] if n == "ref" else SITE_VIEWS)
        if cdir and n != "ref":
            um = f"user '{ROLE}', sslcert '{cdir}/{ROLE}.crt', sslkey '{cdir}/{ROLE}.key'"
        else:
            um = f"user '{cfg.user}', password '{cfg.password}'"
        lines += [
            f"DROP SCHEMA IF EXISTS {schema} CASCADE;",
            f"DROP SERVER IF EXISTS {srv} CASCADE;",
            f"CREATE SERVER {srv} FOREIGN DATA WRAPPER postgres_fdw OPTIONS ({', '.join(opts)});",
            f"CREATE USER MAPPING FOR {cfg.user} SERVER {srv} OPTIONS ({um});",
            f"CREATE SCHEMA {schema};",
            f"IMPORT FOREIGN SCHEMA public LIMIT TO ({', '.join(imported)}) FROM SERVER {srv} INTO {schema};",
        ]
    for t in FRAGMENTED:
        parts = [f"SELECT * FROM public.{t}"] + [f"SELECT * FROM s_{s}.{t}" for s in cfg.remote_sites()]
        lines.append(f"CREATE VIEW all_{t} AS\n    " + "\n    UNION ALL ".join(parts) + ";")
        lines.append(f"COMMENT ON VIEW all_{t} IS 'Khung nhìn toàn cục: {cfg.central} (cục bộ) ∪ "
                     + " ∪ ".join(cfg.remote_sites()) + " (postgres_fdw)';")
    return "\n".join(lines) + "\n"


def main():
    cfg = Config()
    cdir = None
    if cfg.tls_on:
        import tls
        for l in tls.set_hosts(cfg):
            print(f"  DNS nội bộ (trạm trung tâm): {l}")
        with cfg.connect(cfg.central) as c:
            cdir = c.execute("SHOW data_directory").fetchone()[0] + "/" + SUBDIR
    sql = build_sql(cfg, cdir)
    (ROOT / "sql" / "generated_link.sql").write_text(sql, encoding="utf-8")
    with cfg.connect(cfg.central) as c:
        c.execute(sql)
        # thống kê cho bảng ngoài (lấy mẫu ở trạm xa) để bộ tối ưu ước lượng đúng
        for s in cfg.remote_sites():
            for t in ALL_TABLES + SITE_VIEWS:
                c.execute(f"ANALYZE s_{s}.{t}")
        views = c.execute("SELECT string_agg(viewname, ', ' ORDER BY viewname) FROM pg_views "
                          "WHERE schemaname='public' AND viewname LIKE 'all\\_%'").fetchone()[0]
        servers = c.execute("SELECT string_agg(srvname || '=' || array_to_string(srvoptions, ' '), E'\\n    ') "
                            "FROM pg_foreign_server").fetchone()[0]
    print(f"Trạm trung tâm {cfg.label(cfg.central)}")
    print(f"  foreign servers:\n    {servers}")
    print(f"  khung nhìn toàn cục: {views}")
    print("  -> sql/generated_link.sql")


if __name__ == "__main__":
    main()
