"""
Chạy thử TOÀN BỘ hệ trên MỘT máy (Windows / macOS / Linux) — chỉ cần Docker Desktop + Python >= 3.11.

  python tools/onebox.py            dựng 4 trạm, sinh + nạp dữ liệu, check, bench (không trễ + trễ 30 ms),
                                    rồi mở giao diện nhập liệu (8080) và dashboard (8081)
  python tools/onebox.py apps       chỉ mở lại hai giao diện
  python tools/onebox.py stop phuquoc | start phuquoc   tắt / bật một trạm (thử D8)
  python tools/onebox.py down       tắt và xoá cả 4 trạm

Máy A và máy B đều là máy này: tự dò IP LAN của máy và ghi build/deploy.onebox.toml (deploy.toml gốc
giữ nguyên cho lúc demo 2 máy). Trễ 30 ms dùng chế độ proxy (tools/latency_proxy.py) vì Windows không có tc.
"""
import os, socket, subprocess, sys, time, webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"
CFG_OUT = BUILD / "deploy.onebox.toml"
WIN = os.name == "nt"


def detect_ip():
    """IP LAN của máy (container gọi được, client trên máy gọi được). 127.0.0.1 KHÔNG dùng được."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))   # không gửi gói nào, chỉ để hệ điều hành chọn card mạng
        ip = s.getsockname()[0]
    except OSError:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip if not ip.startswith("127.") else "host.docker.internal"


def write_cfg(ip, ref_host="localhost", ref_port=5432, password=None):
    src = (ROOT / "deploy.toml").read_text(encoding="utf-8")
    out, section = [], None
    for line in src.splitlines():
        s = line.strip()
        if s.startswith("["):
            section = s
        if section in ("[machines.A]", "[machines.B]") and s.startswith("ip"):
            line = f'ip = "{ip}"'
        if section == "[db]" and s.startswith("ref_fdw_host"):
            line = f'ref_fdw_host = "{ref_host}"'
        if section == "[db]" and s.startswith("ref_fdw_port"):
            line = f"ref_fdw_port = {ref_port}"
        if section == "[db]" and s.startswith("password") and password:
            line = f'password = "{password}"'
        out.append(line)
    BUILD.mkdir(exist_ok=True)
    CFG_OUT.write_text("\n".join(out) + "\n", encoding="utf-8")


def env():
    e = dict(os.environ, DEPLOY=str(CFG_OUT), PYTHONUTF8="1", DELAY_MODE="proxy")
    return e


def run(args, cwd=ROOT, check=True):
    print(f"\n>>> {' '.join(str(a) for a in args)}", flush=True)
    r = subprocess.run([str(a) for a in args], cwd=cwd, env=env())
    if check and r.returncode != 0:
        sys.exit(f"\nDỪNG: lệnh trên lỗi (mã {r.returncode}). Xem thông báo phía trên.")
    return r.returncode


def py(script, *a, **kw):
    return run([sys.executable, ROOT / script, *a], **kw)


def compose(machine, *a, **kw):
    py("tools/compose.py", machine)
    return run(["docker", "compose", "-f", BUILD / f"compose.{machine}.yml", *a], **kw)


def apps():
    procs = []
    for name in ("entry", "dash"):
        script = ROOT / "app" / f"{name}.py"
        if WIN:   # mỗi giao diện một cửa sổ riêng; đóng cửa sổ là dừng
            procs.append(subprocess.Popen([sys.executable, str(script)], cwd=ROOT, env=env(),
                                          creationflags=subprocess.CREATE_NEW_CONSOLE))
        else:
            (ROOT / "logs").mkdir(exist_ok=True)
            procs.append(subprocess.Popen([sys.executable, str(script)], cwd=ROOT, env=env(),
                                          stdout=open(ROOT / "logs" / f"{name}.log", "w"),
                                          stderr=subprocess.STDOUT, start_new_session=True))
    time.sleep(2.5)
    for url in ("http://localhost:8081", "http://localhost:8080"):
        webbrowser.open(url)
    print("\nNhập liệu: http://localhost:8080   Dashboard: http://localhost:8081")
    print("Đóng hai cửa sổ giao diện (hoặc Ctrl+C trong đó) để dừng." if WIN else
          f"Dừng giao diện: kill {' '.join(str(p.pid) for p in procs)}")


def main():
    a = sys.argv[1:]
    cmd = a[0] if a and not a[0].startswith("--") else "all"
    opts = {k: a[i + 1] for i, k in enumerate(a[:-1]) if k in ("--ip", "--ref-host", "--ref-port", "--password")}
    if cmd == "all" or not CFG_OUT.exists():
        ip = opts.get("--ip") or detect_ip()
        write_cfg(ip, opts.get("--ref-host", "localhost"), int(opts.get("--ref-port", 5432)), opts.get("--password"))
        print(f"IP dùng cho cả máy A và máy B: {ip}  (cấu hình: {CFG_OUT.relative_to(ROOT)})")
    if cmd == "down":
        py("tools/delay.py", "off", check=False)
        compose("A", "down", "-v", check=False); compose("B", "down", "-v", check=False); return
    if cmd in ("stop", "start"):
        run(["docker", cmd, f"hotel_{a[1]}"]); return
    if cmd == "apps":
        apps(); return
    if "--no-docker" not in a:
        run(["docker", "version", "--format", "Docker {{.Server.Version}}"])
        compose("A", "up", "-d", "--build", "--wait")
        compose("B", "up", "-d", "--build", "--wait")
    run([sys.executable, "generate.py", "--size", "lab"], cwd=ROOT / "datagen" / "de06_hotel")
    py("tools/split.py")
    py("tools/wait.py", "120")
    py("tools/load.py")
    py("tools/link.py")
    py("tools/check.py")
    py("tools/delay.py", "off", check=False)
    py("tools/bench.py")
    py("tools/delay.py", "on")
    py("tools/bench.py")
    py("tools/delay.py", "off")
    print("\nXONG: kết quả trong thư mục results\\ (results.csv, check.txt, explain\\, n1/n4/n5.csv)")
    if "--no-apps" not in a:
        apps()


if __name__ == "__main__":
    main()
