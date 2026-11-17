#!/usr/bin/env python3
"""Chạy nền giao diện nhập liệu (8501) và dashboard (8502) cho `make all`; `make down` tắt chúng.

    python tools/apps.py start|stop
"""
import os
import signal
import subprocess
import sys
import time

from common import RESULTS, ROOT

APPS = {"entry": 8501, "dash": 8502}
PIDS = ROOT / "build" / "pids"


def start():
    PIDS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "logs").mkdir(parents=True, exist_ok=True)
    stop(quiet=True)
    for name, port in APPS.items():
        log = open(RESULTS / "logs" / f"{name}.log", "w", encoding="utf-8")
        kw = {"creationflags": 0x00000008 | 0x00000200} if os.name == "nt" else {"start_new_session": True}
        p = subprocess.Popen([sys.executable, "-m", "streamlit", "run", str(ROOT / "app" / f"{name}.py"),
                              "--server.port", str(port), "--server.headless", "true",
                              "--browser.gatherUsageStats", "false"],
                             cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, env=os.environ.copy(), **kw)
        (PIDS / f"{name}.pid").write_text(str(p.pid))
        print(f"  {name:<5} -> http://localhost:{port}  (pid {p.pid}, log results/logs/{name}.log)")
    time.sleep(2)


def stop(quiet=False):
    if not PIDS.exists():
        return
    for f in PIDS.glob("*.pid"):
        pid = int(f.read_text())
        try:
            if os.name == "nt":
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True)
            else:
                os.killpg(pid, signal.SIGTERM)
            if not quiet:
                print(f"  đã tắt {f.stem} (pid {pid})")
        except (ProcessLookupError, PermissionError):
            pass
        f.unlink()


if __name__ == "__main__":
    {"start": start, "stop": stop}[sys.argv[1] if len(sys.argv) > 1 else "start"]()
