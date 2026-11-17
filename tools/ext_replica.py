#!/usr/bin/env python3
"""PHẦN MỞ RỘNG E1 (ngoài yêu cầu đề) — bản sao dự phòng cho một mảnh + chuyển đọc khi trạm chính chết.

Giải quyết giới hạn "một trạm chết thì dữ liệu vùng đó không đọc được" (D8).
Bản sao là một PostgreSQL ở chế độ hot standby, nhận WAL của trạm chính qua streaming replication
(sao chép vật lý, bất đồng bộ — Giáo trình Chương 5). Bản sao chỉ đọc, nên mọi lệnh ghi vẫn phải vào trạm chính.

    python tools/ext_replica.py up       [trạm]   # tạo bản sao (pg_basebackup -R qua LAN) + replication slot
    python tools/ext_replica.py status   [trạm]   # độ trễ sao chép, số dòng chính/bản sao, fdw đang trỏ đâu
    python tools/ext_replica.py failover [trạm]   # srv_<trạm> ở trạm trung tâm -> bản sao (chỉ đọc)
    python tools/ext_replica.py failback [trạm]   # srv_<trạm> -> trạm chính
    python tools/ext_replica.py watch    [trạm]   # tự động: trạm chính mất -> failover; sống lại -> failback
    python tools/ext_replica.py down     [trạm]   # xoá bản sao + slot

Trạm mặc định = trạm đầu tiên có mục [ext.replica.<trạm>] trong deploy.toml (hiện là phuquoc, bản sao ở máy A).
Không sửa gì của hệ chính: `make all`, `make check`, D1–D8 chạy y như khi chưa có phần mở rộng.
"""
import subprocess
import sys
import time

from common import Config, die, run

NETWORK = "cs5104_net"
HBA_MARK = "# cs5104-ext: cho phép bản sao dự phòng kết nối replication"


def slot_name(site: str) -> str:
    return f"cs5104_{site}_replica"


def pick(cfg: Config, site: str | None) -> tuple[str, str]:
    if not cfg.replicas:
        die(f"{cfg.path.name} chưa có mục [ext.replica.<trạm>]")
    if site is None:
        rep = next(iter(cfg.replicas))
        return cfg.replicas[rep]["of"], rep
    rep = f"{site}_replica"
    if rep not in cfg.replicas:
        die(f"{cfg.path.name} không có [ext.replica.{site}]")
    return site, rep


def try_connect(cfg: Config, name: str, timeout: int = 2):
    try:
        return cfg.connect(name, timeout=timeout)
    except Exception:  # noqa: BLE001
        return None


def container_state(name: str) -> str:
    r = subprocess.run(["docker", "inspect", "-f", "{{.State.Running}}", name], capture_output=True, text=True)
    return {"true": "running", "false": "stopped"}.get(r.stdout.strip(), "-")


# ------------------------------------------------------------------ up
def prepare_primary(cfg: Config, site: str):
    """Ở trạm chính: thêm dòng pg_hba cho replication từ máy khác (qua SQL, không cần vào máy B), tạo slot."""
    with cfg.connect(site) as c:
        hba = c.execute("SELECT current_setting('hba_file')").fetchone()[0]
        content = c.execute("SELECT pg_read_file(%s)", [hba]).fetchone()[0]
        if HBA_MARK not in content:
            # COPY ... TO PROGRAM chạy trong container của trạm chính (quyền superuser) — nối thêm 2 dòng vào pg_hba.conf
            # mỗi dòng của tệp = một hàng kết quả (COPY text sẽ escape ký tự xuống dòng nằm trong một giá trị)
            c.execute(f"COPY (SELECT unnest(ARRAY['', $q${HBA_MARK}$q$, "
                      f"'host replication all all scram-sha-256'])) TO PROGRAM 'cat >> {hba}'")
            c.execute("SELECT pg_reload_conf()")
            print(f"  pg_hba.conf của {site}: thêm 'host replication all all scram-sha-256', reload")
        slot = slot_name(site)
        if not c.execute("SELECT 1 FROM pg_replication_slots WHERE slot_name = %s", [slot]).fetchone():
            c.execute("SELECT pg_create_physical_replication_slot(%s, true)", [slot])
            print(f"  replication slot {slot} (trạm chính giữ WAL tới khi bản sao nhận xong)")


def up(cfg: Config, site: str, rep: str):
    if cfg.machine_of(rep) != cfg.here:
        die(f"bản sao {rep} đặt ở máy {cfg.machine_of(rep)}, hãy chạy lệnh trên máy đó")
    c = cfg.container(rep)
    if container_state(c) == "running":
        print(f"  {rep} đã chạy")
        return wait_standby(cfg, rep)
    if container_state(c) == "stopped":
        run(["docker", "start", c])
        return wait_standby(cfg, rep)
    if not try_connect(cfg, site):
        die(f"không kết nối được trạm chính {cfg.label(site)} — bản sao phải được tạo khi trạm chính sống")
    prepare_primary(cfg, site)
    host, port = cfg.docker_addr(site, from_node=rep)
    pgdata = "/var/lib/postgresql/18/docker"
    script = (
        'set -e; D="$PGDATA"; '
        'if [ ! -s "$D/PG_VERSION" ]; then '
        '  echo "pg_basebackup từ $PRIMARY_HOST:$PRIMARY_PORT ..."; mkdir -p "$D"; chmod 700 "$D"; '
        '  pg_basebackup -h "$PRIMARY_HOST" -p "$PRIMARY_PORT" -U "$PGUSER" -D "$D" -R -X stream -S "$SLOT" -c fast; '
        'fi; '
        # bản sao phải có max_connections, max_prepared_transactions >= trạm chính (yêu cầu của hot standby)
        'exec postgres -D "$D" -c hot_standby=on -c max_prepared_transactions=20 '
        '-c max_connections=200 -c shared_buffers=256MB'
    )
    run(["docker", "run", "-d", "--name", c, "--hostname", rep, "--network", NETWORK,
         "-p", f"0.0.0.0:{cfg.node(rep)['port']}:5432",
         "--user", "postgres", "--entrypoint", "bash",
         "-e", f"PGDATA={pgdata}", "-e", f"PGUSER={cfg.user}", "-e", f"PGPASSWORD={cfg.password}",
         # E3: trạm chính từ chối replication không mã hoá => pg_basebackup và walreceiver đi qua TLS
         "-e", f"PGSSLMODE={'require' if cfg.tls_on else 'prefer'}",
         "-e", f"PRIMARY_HOST={host}", "-e", f"PRIMARY_PORT={port}", "-e", f"SLOT={slot_name(site)}",
         "-e", "TZ=Asia/Ho_Chi_Minh",
         "-v", f"{cfg.volume(rep)}:/var/lib/postgresql",
         "--add-host", "host.docker.internal:host-gateway",
         "--label", "cs5104=de06-ext",
         cfg.image, "-c", script])
    wait_standby(cfg, rep)


def wait_standby(cfg: Config, rep: str, timeout: int = 300):
    t0 = time.time()
    while time.time() - t0 < timeout:
        conn = try_connect(cfg, rep)
        if conn:
            with conn:
                rec = conn.execute("SELECT pg_is_in_recovery()").fetchone()[0]
            print(f"  {rep} sẵn sàng · hot standby = {rec} · {cfg.label(rep)}")
            return
        if container_state(cfg.container(rep)) != "running":
            subprocess.run(["docker", "logs", "--tail", "30", cfg.container(rep)])
            die(f"container {cfg.container(rep)} đã dừng (xem log ở trên)")
        time.sleep(2)
    die(f"{rep} không sẵn sàng sau {timeout}s")


# ------------------------------------------------------------------ fdw
def fdw_target(cfg: Config, site: str) -> str:
    with cfg.connect(cfg.central) as c:
        opts = c.execute("SELECT srvoptions FROM pg_foreign_server WHERE srvname = %s", [f"srv_{site}"]).fetchone()
    if not opts:
        return "(chưa có srv — chạy make link)"
    d = dict(o.split("=", 1) for o in opts[0])
    return f"{d.get('host')}:{d.get('port')}"


def point_fdw(cfg: Config, site: str, node: str) -> str:
    host, port = cfg.docker_addr(node)
    if cfg.tls_on:
        # E3: srv_* luôn gọi bằng TÊN (verify-full). Chuyển đọc = đổi bản ghi DNS nội bộ <trạm>.<domain> sang
        # IP của bản sao (bản sao có cùng chứng chỉ máy chủ do pg_basebackup chép cả thư mục dữ liệu).
        import tls
        tls.set_hosts(cfg, override={site: node})
        with cfg.connect(cfg.central) as c:
            c.execute(f"ALTER SERVER srv_{site} OPTIONS (SET port '{port}')")
        return f"{cfg.fqdn(site)} -> {host}:{port}"
    with cfg.connect(cfg.central) as c:
        c.execute(f"ALTER SERVER srv_{site} OPTIONS (SET host '{host}', SET port '{port}')")
    return f"{host}:{port}"


def failover(cfg: Config, site: str, rep: str):
    conn = try_connect(cfg, rep)
    if not conn:
        die(f"bản sao {rep} không kết nối được — chạy make ext-replica trước")
    conn.close()
    tgt = point_fdw(cfg, site, rep)
    print(f"FAILOVER: srv_{site} ở trạm trung tâm -> {tgt} ({cfg.label(rep)}, CHỈ ĐỌC)")
    print("  Q2–Q5 đọc được mảnh của trạm này từ bản sao; ghi vào trạm vẫn báo lỗi (không ghi nhầm sang bản sao).")


def failback(cfg: Config, site: str):
    tgt = point_fdw(cfg, site, site)
    print(f"FAILBACK: srv_{site} -> {tgt} ({cfg.label(site)})")


def watch(cfg: Config, site: str, rep: str, every: float = 1.0):
    print(f"Theo dõi {site} mỗi {every:.0f} s (Ctrl+C để dừng). Chính chết -> failover; chính sống lại -> failback.")
    primary_target = "%s:%s" % cfg.docker_addr(site)
    on_replica = fdw_target(cfg, site) != primary_target
    try:
        while True:
            conn = try_connect(cfg, site, timeout=1)
            alive = conn is not None
            if conn:
                conn.close()
            ts = time.strftime("%H:%M:%S")
            if not alive and not on_replica:
                print(f"[{ts}] {site} MẤT KẾT NỐI", flush=True)
                failover(cfg, site, rep)
                on_replica = True
            elif alive and on_replica:
                print(f"[{ts}] {site} đã sống lại", flush=True)
                failback(cfg, site)
                on_replica = False
            time.sleep(every)
    except KeyboardInterrupt:
        print("\ndừng theo dõi; srv_%s đang trỏ tới %s" % (site, fdw_target(cfg, site)))


# ------------------------------------------------------------------ status / down
def status(cfg: Config, site: str, rep: str):
    print(f"Trạm chính : {cfg.label(site)}")
    print(f"Bản sao    : {cfg.label(rep)} · container {container_state(cfg.container(rep))}")
    print(f"srv_{site} ở trạm trung tâm đang trỏ tới: {fdw_target(cfg, site)}")
    p, r = try_connect(cfg, site), try_connect(cfg, rep)
    n_p = n_r = None
    if p:
        with p:
            rows = p.execute("SELECT application_name, client_addr::text, state, sync_state, "
                             "pg_wal_lsn_diff(sent_lsn, replay_lsn)::bigint, replay_lag::text "
                             "FROM pg_stat_replication").fetchall()
            n_p = p.execute("SELECT count(*) FROM booking").fetchone()[0]
            prep = p.execute("SELECT slot_name, active FROM pg_replication_slots").fetchall()
        print(f"  [chính]   booking = {n_p} · slots = {prep}")
        for a, ip, st, sy, lagb, lagt in rows:
            print(f"            walsender → {a or '?'} @ {ip}: {st}/{sy}, chưa phát lại {lagb} byte, replay_lag {lagt}")
        if not rows:
            print("            (không có bản sao nào đang kết nối)")
    else:
        print("  [chính]   MẤT KẾT NỐI")
    if r:
        with r:
            rec, lsn, lag = r.execute("SELECT pg_is_in_recovery(), pg_last_wal_replay_lsn()::text, "
                                      "(now() - pg_last_xact_replay_timestamp())::text").fetchone()
            n_r = r.execute("SELECT count(*) FROM booking").fetchone()[0]
        print(f"  [bản sao] booking = {n_r} · in_recovery = {rec} · đã phát lại tới {lsn} · "
              f"giao dịch cuối cách đây {lag}")
    else:
        print("  [bản sao] MẤT KẾT NỐI")
    if n_p is not None and n_r is not None:
        print(f"  {'KHỚP' if n_p == n_r else 'CHƯA KHỚP (đang bắt kịp)'}: chính {n_p} · bản sao {n_r}")


def down(cfg: Config, site: str, rep: str):
    subprocess.run(["docker", "rm", "-f", cfg.container(rep)], capture_output=True)
    subprocess.run(["docker", "volume", "rm", "-f", cfg.volume(rep)], capture_output=True)
    print(f"  đã xoá container + volume {rep}")
    p = try_connect(cfg, site)
    if p:
        with p:
            p.execute("SELECT pg_drop_replication_slot(slot_name) FROM pg_replication_slots "
                      "WHERE slot_name = %s AND NOT active", [slot_name(site)])
        print(f"  đã xoá slot {slot_name(site)} ở {site}")
    c = try_connect(cfg, cfg.central)
    if c:
        c.close()
        if fdw_target(cfg, site) != "%s:%s" % cfg.docker_addr(site):
            failback(cfg, site)


def main():
    if len(sys.argv) < 2:
        die(__doc__)
    cfg = Config()
    cmd = sys.argv[1]
    site, rep = pick(cfg, sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] else None)
    {"up": lambda: up(cfg, site, rep), "status": lambda: status(cfg, site, rep),
     "failover": lambda: failover(cfg, site, rep), "failback": lambda: failback(cfg, site),
     "watch": lambda: watch(cfg, site, rep), "down": lambda: down(cfg, site, rep)}.get(cmd, lambda: die(__doc__))()


if __name__ == "__main__":
    main()
