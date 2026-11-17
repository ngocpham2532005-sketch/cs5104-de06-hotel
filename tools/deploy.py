#!/usr/bin/env python3
"""Bật/tắt các trạm PostgreSQL của MỘT máy theo deploy.toml (chỉ thư viện chuẩn + docker CLI).

    python tools/deploy.py build            # build image cs5104-pg18
    python tools/deploy.py up A|B           # bật đúng các trạm của máy (tạo mới nếu chưa có), chờ sẵn sàng
    python tools/deploy.py down A|B         # xoá container + volume của máy
    python tools/deploy.py stop  <trạm>     # tắt một trạm (demo D8)
    python tools/deploy.py start <trạm>     # bật lại
    python tools/deploy.py status

Chạy được trên macOS, Linux và Windows (Docker Desktop + Python >= 3.11).
"""
import subprocess
import sys
import time

from common import Config, die, run

NETWORK = "cs5104_net"


def docker_ok():
    r = subprocess.run(["docker", "info", "--format", "{{.ServerVersion}}"], capture_output=True, text=True)
    if r.returncode != 0:
        die("Docker chưa chạy. Hãy mở Docker Desktop rồi chạy lại.")


def exists(name: str) -> bool:
    r = subprocess.run(["docker", "ps", "-a", "--filter", f"name=^/{name}$", "--format", "{{.Names}}"],
                       capture_output=True, text=True)
    return r.stdout.strip() == name


def running(name: str) -> bool:
    r = subprocess.run(["docker", "inspect", "-f", "{{.State.Running}}", name], capture_output=True, text=True)
    return r.stdout.strip() == "true"


def build(cfg: Config):
    docker_ok()
    from common import ROOT
    run(["docker", "build", "-q", "-t", cfg.image, str(ROOT / "docker")])


def image_exists(cfg: Config) -> bool:
    return subprocess.run(["docker", "image", "inspect", cfg.image], capture_output=True).returncode == 0


def wait_ready(cfg: Config, name: str, timeout: int = 120):
    """Chờ tới khi trạm nhận kết nối TCP (bỏ qua giai đoạn initdb chỉ nghe unix socket)."""
    c = cfg.container(name)
    t0 = time.time()
    while time.time() - t0 < timeout:
        r = subprocess.run(["docker", "exec", "-e", f"PGPASSWORD={cfg.password}", c, "psql",
                            "-h", "127.0.0.1", "-U", cfg.user, "-d", cfg.db, "-Atc", "select 1"],
                           capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip() == "1":
            print(f"  {name:<9} sẵn sàng  ({cfg.label(name)})")
            return
        time.sleep(1)
    die(f"trạm {name} không sẵn sàng sau {timeout}s")


def up(cfg: Config, machine: str):
    docker_ok()
    if machine not in cfg.machines:
        die(f"máy {machine} không có trong {cfg.path.name}")
    if not image_exists(cfg):
        build(cfg)
    if subprocess.run(["docker", "network", "inspect", NETWORK], capture_output=True).returncode != 0:
        run(["docker", "network", "create", NETWORK])
    names = cfg.nodes_on(machine)
    for n in names:
        c = cfg.container(n)
        port = cfg.node(n)["port"]
        if exists(c):
            if not running(c):
                run(["docker", "start", c])
            continue
        run(["docker", "run", "-d", "--name", c, "--hostname", n, "--network", NETWORK,
             "-p", f"0.0.0.0:{port}:5432",
             "-e", f"POSTGRES_PASSWORD={cfg.password}", "-e", f"POSTGRES_USER={cfg.user}",
             "-e", f"POSTGRES_DB={cfg.db}", "-e", "TZ=Asia/Ho_Chi_Minh",
             "-v", f"{cfg.volume(n)}:/var/lib/postgresql",
             "--cap-add", "NET_ADMIN",
             "--add-host", "host.docker.internal:host-gateway",
             "--label", "cs5104=de06",
             cfg.image,
             "-c", "max_prepared_transactions=20",     # 2PC khi thêm đoàn tour (ghi 4 bản sao)
             "-c", "shared_buffers=256MB",
             "-c", "max_connections=200"])
    for n in names:
        wait_ready(cfg, n)
    print(f"Máy {machine} ({cfg.machines[machine]['os']}): {', '.join(names)} đang chạy.")


def down(cfg: Config, machine: str):
    docker_ok()
    # gồm cả bản sao dự phòng của phần mở rộng E1 (nếu có trên máy này)
    for n in cfg.nodes_on(machine) + [r for r in cfg.replicas if cfg.machine_of(r) == machine]:
        c = cfg.container(n)
        if exists(c):
            run(["docker", "rm", "-f", c])
        subprocess.run(["docker", "volume", "rm", "-f", cfg.volume(n)], capture_output=True)
    print(f"Đã gỡ các trạm của máy {machine}.")


def stop(cfg: Config, site: str):
    run(["docker", "stop", "-t", "2", cfg.container(site)])
    print(f"Đã TẮT trạm {cfg.label(site)}")


def start(cfg: Config, site: str):
    run(["docker", "start", cfg.container(site)])
    wait_ready(cfg, site)


def status(cfg: Config):
    for n in cfg.nodes():
        c = cfg.container(n)
        st = "running" if running(c) else ("stopped" if exists(c) else "-")
        mark = "(máy này)" if cfg.machine_of(n) == cfg.here else ""
        print(f"  {n:<9} {st:<8} {cfg.label(n)} {mark}")


def main():
    if len(sys.argv) < 2:
        die(__doc__)
    cfg = Config()
    cmd, arg = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else None)
    if cmd == "build":
        build(cfg)
    elif cmd == "up":
        up(cfg, arg or cfg.here)
    elif cmd == "down":
        down(cfg, arg or cfg.here)
    elif cmd == "stop":
        stop(cfg, arg)
    elif cmd == "start":
        start(cfg, arg)
    elif cmd == "status":
        status(cfg)
    else:
        die(__doc__)


if __name__ == "__main__":
    main()
