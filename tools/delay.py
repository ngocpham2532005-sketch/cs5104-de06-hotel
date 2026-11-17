#!/usr/bin/env python3
"""Giả lập trễ mạng 30 ms giữa trạm trung tâm và các trạm xa (tc netem trong container trạm trung tâm).

    python tools/delay.py on|off|status

Cách làm: qdisc `prio` 4 băng ở eth0 của container trung tâm; băng 4 gắn `netem delay 30ms`;
bộ lọc u32 chỉ đưa vào băng 4 các gói có ĐÍCH là trạm xa (dalat qua mạng Docker, máy B qua IP LAN).
=> mỗi vòng khứ hồi trung tâm↔trạm xa chậm thêm 30 ms; kết nối của client tới trạm trung tâm,
   tới CSDL đối chứng và truy vấn chạy tại chính một trạm (Q1 ở dalat) không bị ảnh hưởng.
Chỉ cần chạy ở máy A.

PHƯƠNG ÁN DỰ PHÒNG — DELAY_MODE=proxy (khi không chạy được tc trong container, vd. thiếu NET_ADMIN):
    DELAY_MODE=proxy make delay-on
chạy tools/latency_proxy.py trên máy A (cổng = cổng trạm + 100) rồi ALTER SERVER srv_<trạm> trỏ vào
proxy qua host.docker.internal; `make delay-off` tắt proxy và trả srv_<trạm> về địa chỉ cũ.
Lưu ý: không dùng chung với `make ext-failover` (cùng sửa srv_phuquoc).
"""
import json
import os
import signal
import subprocess
import sys

from common import ROOT, Config, die

MODE = os.environ.get("DELAY_MODE", "tc").lower()
PROXY_STATE = ROOT / "build" / "delay_proxy.json"
PROXY_OFFSET = 100


def sh(cfg: Config, script: str, check=True) -> str:
    r = subprocess.run(["docker", "exec", cfg.container(cfg.central), "sh", "-c", script],
                       capture_output=True, text=True)
    if check and r.returncode != 0:
        die(f"tc lỗi: {r.stderr.strip()}")
    return r.stdout


def target_ips(cfg: Config) -> dict:
    ips = {}
    for s in cfg.remote_sites():
        host, _ = cfg.docker_addr(s)
        out = sh(cfg, f"getent ahostsv4 {host} | awk 'NR==1{{print $1}}'").strip()
        if not out:
            die(f"không phân giải được {host}")
        ips[s] = out
    return ips


def on(cfg: Config):
    off(cfg, quiet=True)
    if MODE == "proxy":
        return proxy_on(cfg)
    ips = target_ips(cfg)
    script = [f"tc qdisc add dev eth0 root handle 1: prio bands 4",
              f"tc qdisc add dev eth0 parent 1:4 handle 40: netem delay {cfg.delay_ms}ms"]
    for ip in sorted(set(ips.values())):
        script.append(f"tc filter add dev eth0 protocol ip parent 1:0 prio 1 u32 match ip dst {ip}/32 flowid 1:4")
    sh(cfg, " && ".join(script))
    print(f"TRỄ BẬT: +{cfg.delay_ms} ms mỗi vòng khứ hồi từ {cfg.central} tới " +
          ", ".join(f"{s} ({ip})" for s, ip in ips.items()))


def off(cfg: Config, quiet=False):
    sh(cfg, "tc qdisc del dev eth0 root 2>/dev/null || true", check=False)
    proxy_off(cfg)
    if not quiet:
        print("TRỄ TẮT.")


def is_on(cfg: Config) -> bool:
    return PROXY_STATE.exists() or "netem" in sh(cfg, "tc qdisc show dev eth0", check=False)


# ---------------------------------------------------------------- DELAY_MODE=proxy
def set_servers(cfg: Config, addrs: dict):
    with cfg.connect(cfg.central) as c:
        for s, (host, port) in addrs.items():
            c.execute(f"ALTER SERVER srv_{s} OPTIONS (SET host '{host}', SET port '{port}')")


def proxy_on(cfg: Config):
    routes, addrs = [], {}
    for s in cfg.remote_sites():
        host, port = cfg.host_addr(s)                     # proxy chạy trên máy A, tới trạm như mọi tool khác
        lport = int(cfg.node(s)["port"]) + PROXY_OFFSET
        routes.append(f"{lport}:{host}:{port}")
        addrs[s] = ("host.docker.internal", lport)       # container trạm trung tâm tới proxy trên máy chủ
    PROXY_STATE.parent.mkdir(parents=True, exist_ok=True)
    log = open(ROOT / "build" / "delay_proxy.log", "w", encoding="utf-8")
    kw = {"creationflags": 0x00000008 | 0x00000200} if os.name == "nt" else {"start_new_session": True}
    p = subprocess.Popen([sys.executable, str(ROOT / "tools" / "latency_proxy.py"), "--delay", str(cfg.delay_ms),
                          *routes], stdout=log, stderr=subprocess.STDOUT, **kw)
    PROXY_STATE.write_text(json.dumps({"pid": p.pid, "routes": routes}), encoding="utf-8")
    import time
    time.sleep(0.5)
    if p.poll() is not None:
        PROXY_STATE.unlink()
        die("proxy không chạy được, xem build/delay_proxy.log")
    set_servers(cfg, addrs)
    print(f"TRỄ BẬT (proxy, pid {p.pid}): +{cfg.delay_ms} ms mỗi vòng khứ hồi từ {cfg.central} tới " +
          ", ".join(f"{s} (qua :{a[1]})" for s, a in addrs.items()))


def proxy_off(cfg: Config):
    if not PROXY_STATE.exists():
        return
    st = json.loads(PROXY_STATE.read_text(encoding="utf-8"))
    set_servers(cfg, {s: cfg.docker_addr(s) for s in cfg.remote_sites()})
    try:
        os.kill(st["pid"], signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        pass
    PROXY_STATE.unlink()


def main():
    cfg = Config()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "on":
        on(cfg)
    elif cmd == "off":
        off(cfg)
    else:
        print("trễ đang", "BẬT" if is_on(cfg) else "TẮT", "(proxy)" if PROXY_STATE.exists() else "")
        print(sh(cfg, "tc qdisc show dev eth0; tc filter show dev eth0", check=False))


if __name__ == "__main__":
    main()
