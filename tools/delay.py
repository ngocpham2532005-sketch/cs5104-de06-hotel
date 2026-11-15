"""
make delay-on / delay-off — thêm trễ 30 ms (deploy.toml [app].delay_ms) trên đường từ trạm trung tâm
tới máy B. Chạy ở máy A.

DELAY_MODE=tc (mặc định): `tc netem` trong container trạm trung tâm, CHỈ cho gói đi tới IP máy B
    (lọc u32 theo đích) => postgres_fdw tới phuquoc/danang chậm thêm 30 ms mỗi vòng khứ hồi;
    tới dalat (cùng máy A) không đổi. Container được bật cap NET_ADMIN, image có iproute2.
DELAY_MODE=proxy: chạy tools/latency_proxy.py trên máy A và trỏ srv_<trạm máy B> vào proxy
    (dùng khi không chạy được tc, ví dụ khi thử trên một máy).
"""
import os, signal, subprocess, sys, time
from cfg import CENTRAL, CFG, RESULTS, ROOT, SITES, connect, site

MODE = os.environ.get("DELAY_MODE", "tc")
DELAY = int(CFG["app"].get("delay_ms", 30))
STATE = RESULTS / ".delay"
PIDF = RESULTS / ".delay_proxy.pid"
B_SITES = [s for s in SITES if site(s)["machine"] != site(CENTRAL)["machine"]]
CONTAINER = f"hotel_{CENTRAL}"


def sh(cmd, check=True):
    print("$", cmd)
    return subprocess.run(cmd, shell=True, check=check)


def tc_on():
    ips = sorted({site(s)["ip"] for s in B_SITES})
    filters = "; ".join(f"tc filter add dev eth0 protocol ip parent 1:0 prio 1 u32 match ip dst {ip}/32 flowid 1:3"
                        for ip in ips)
    sh(f"docker exec {CONTAINER} sh -c 'tc qdisc del dev eth0 root 2>/dev/null; "
       f"tc qdisc add dev eth0 root handle 1: prio && "
       f"tc qdisc add dev eth0 parent 1:3 handle 30: netem delay {DELAY}ms && {filters}'")
    sh(f"docker exec {CONTAINER} tc qdisc show dev eth0")


def tc_off():
    sh(f"docker exec {CONTAINER} sh -c 'tc qdisc del dev eth0 root 2>/dev/null || true'")


def set_servers(proxy):
    with connect(CENTRAL) as c:
        for s in B_SITES:
            i = site(s)
            host, port = (site(CENTRAL)["ip"], i["port"] + 100) if proxy else (i["ip"], i["port"])
            c.execute(f"ALTER SERVER srv_{s} OPTIONS (SET host '{host}', SET port '{port}')")


def proxy_on():
    proxy_off(quiet=True)
    routes = [f"{site(s)['port'] + 100}:{site(s)['ip']}:{site(s)['port']}" for s in B_SITES]
    extra = ({"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {"start_new_session": True})
    p = subprocess.Popen([sys.executable, str(ROOT / "tools" / "latency_proxy.py"), "--delay", str(DELAY), *routes],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **extra)
    PIDF.write_text(str(p.pid)); time.sleep(0.5)
    set_servers(proxy=True)


def proxy_off(quiet=False):
    if PIDF.exists():
        try:
            pid = int(PIDF.read_text())
            if os.name == "nt":
                os.kill(pid, signal.SIGTERM)        # Windows: TerminateProcess
            else:
                os.killpg(pid, signal.SIGTERM)
        except (ProcessLookupError, ValueError, PermissionError, OSError):
            pass
        PIDF.unlink()
    if not quiet:
        set_servers(proxy=False)


def main():
    RESULTS.mkdir(exist_ok=True)
    on = sys.argv[1:] == ["on"]
    if MODE == "proxy":
        proxy_on() if on else proxy_off()
    else:
        tc_on() if on else tc_off()
    STATE.write_text(str(DELAY if on else 0))
    print(f"Trễ {'BẬT ' + str(DELAY) + ' ms' if on else 'TẮT'} ({MODE}) trên đường {CENTRAL} -> {', '.join(B_SITES)}")


if __name__ == "__main__":
    main()
