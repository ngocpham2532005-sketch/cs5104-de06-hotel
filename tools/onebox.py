#!/usr/bin/env python3
"""Chạy thử TOÀN BỘ hệ trên MỘT máy, không cần `make` (macOS, Linux, Windows).

    python tools/onebox.py                 # venv → build → up A + B → data → load → link → check → bench → giao diện
    python tools/onebox.py apps            # mở lại nhập liệu :8501 và dashboard :8502
    python tools/onebox.py q [Q2 Q3 -e]    # chạy Q1–Q5 cho demo
    python tools/onebox.py stop phuquoc    # D8: tắt / bật một trạm
    python tools/onebox.py start phuquoc
    python tools/onebox.py status | down
    python tools/onebox.py --dry-run       # chỉ in các bước sẽ chạy

Dùng deploy.local.toml (máy A = máy B = máy này, "máy B" được gọi qua host.docker.internal), tương đương
`make all DEPLOY=deploy.local.toml` + `make up MACHINE=B DEPLOY=deploy.local.toml`. Không sửa deploy.toml.
Khi demo thật trên 2 máy vẫn dùng `make all` như README.
(Ý tưởng lấy từ bản thử nghiệm của thành viên nhóm, viết lại theo các tool sẵn có của repo này.)
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEPLOY = "deploy.local.toml"
VPY = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
GEN = "datagen/de06_hotel/generate.py"
DRY = "--dry-run" in sys.argv


def step(py, *args, machine="A", check=True):
    env = dict(os.environ, DEPLOY=DEPLOY, MACHINE=machine, PYTHONUTF8="1")
    cmd = [str(py), *args]
    print(f"\n>>> [máy {machine}] {' '.join(args)}", flush=True)
    if DRY:
        return 0
    r = subprocess.run(cmd, cwd=ROOT, env=env)
    if check and r.returncode != 0:
        sys.exit(f"Bước lỗi (mã {r.returncode}): {' '.join(args)}")
    return r.returncode


def venv():
    if not VPY.exists():
        step(sys.executable, "-m", "venv", ".venv")
    step(VPY, "-m", "pip", "install", "-q", "--upgrade", "pip")
    step(VPY, "-m", "pip", "install", "-q", "-r", "requirements.txt")


def all_():
    if not DRY and subprocess.run(["docker", "ps", "-q", "-f", "name=^/cs5104_nhatrang$"],
                                  capture_output=True, text=True).stdout.strip() and "--force" not in sys.argv:
        sys.exit("Máy này đang chạy các trạm cs5104_* (có thể của cấu hình 2 máy).\n"
                 "Gỡ trước: `python tools/onebox.py down` (hoặc make down), hoặc thêm --force để dùng lại.")
    venv()
    step(sys.executable, "tools/deploy.py", "build")
    step(sys.executable, "tools/deploy.py", "up", "B", machine="B")
    step(sys.executable, "tools/deploy.py", "up", "A")
    step(VPY, "tools/tls.py", "secure")                 # E3: TLS + chứng chỉ cho mọi nút
    step(sys.executable, GEN, "--size", "mini")
    step(sys.executable, GEN, "--size", "lab")
    for t in ("load", "link", "check", "bench"):
        step(VPY, f"tools/{t}.py")
    step(VPY, "tools/apps.py", "start")
    print("\nXong. Nhập liệu: http://localhost:8501   Dashboard: http://localhost:8502\n"
          "D8: python tools/onebox.py stop phuquoc  …  start phuquoc")


def main():
    args = [a for a in sys.argv[1:] if a not in ("--dry-run", "--force")]
    cmd = args[0] if args else "all"
    if cmd == "all":
        all_()
    elif cmd == "apps":
        step(VPY, "tools/apps.py", "start")
    elif cmd == "q":
        step(VPY, "tools/demo.py", *args[1:])
    elif cmd in ("stop", "start") and len(args) == 2:
        site = args[1]
        step(sys.executable, "tools/deploy.py", cmd, site, machine="B" if site in ("phuquoc", "danang") else "A")
    elif cmd == "status":
        step(sys.executable, "tools/deploy.py", "status")
    elif cmd == "down":
        if VPY.exists():
            step(VPY, "tools/apps.py", "stop", check=False)
        step(sys.executable, "tools/deploy.py", "down", "A")
        step(sys.executable, "tools/deploy.py", "down", "B", machine="B")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
