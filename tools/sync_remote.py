#!/usr/bin/env python3
"""Cập nhật mã nguồn của repo sang một máy khác qua SSH (vd. máy B, Windows hoặc Linux), rồi kiểm tra hai đầu khớp.

    python tools/sync_remote.py user@host C:/cs5104/de06_hotel_ddb [--key ~/.ssh/id] [--python python]
    make sync-remote SSH=user@host DEST=C:/cs5104/de06_hotel_ddb KEY=~/.ssh/id

- Gói mã nguồn (không gói .venv, build/, dữ liệu sinh ra, nhật ký) thành một tệp tar, gửi bằng scp, giải nén bằng `tar`
  (có sẵn trên Windows 10+, macOS, Linux). Không đụng tới build/ ở máy đích: CSR/chứng chỉ của máy đó giữ nguyên.
- Sau khi giải nén, chạy `tools/tls_site.py --version` ở máy đích và so mã băm với máy này.
Khi repo đã ở GitHub, cách chuẩn là `git pull` ở mỗi máy (tag `final`); script này dùng khi máy đích chưa có git.
Thông tin SSH (user, host, khoá) chỉ truyền qua tham số, không ghi vào repo.
"""
import argparse
import io
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".git", ".venv", "build", "__pycache__", "output", "logs"}
SKIP_FILES = {".DS_Store", "events.jsonl", "2pc_coordinator.jsonl", ".sync.tar"}


def pack() -> bytes:
    buf = io.BytesIO()
    n = 0
    with tarfile.open(fileobj=buf, mode="w") as t:
        for p in sorted(ROOT.rglob("*")):
            rel = p.relative_to(ROOT)
            if (any(part in SKIP_DIRS for part in rel.parts) or p.name in SKIP_FILES or not p.is_file()
                    or p.name.startswith("e3_site_")):      # nhật ký E3 của từng máy: không ghi đè sang máy khác
                continue
            t.add(p, arcname=rel.as_posix())
            n += 1
    print(f"  gói {n} tệp ({buf.tell() // 1024} KB)")
    return buf.getvalue()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ssh", help="user@host")
    ap.add_argument("dest", help="thư mục repo ở máy đích, vd. C:/cs5104/de06_hotel_ddb")
    ap.add_argument("--key", help="khoá SSH")
    ap.add_argument("--python", default="python", help="lệnh python ở máy đích")
    a = ap.parse_args()
    if not a.ssh or not a.dest:
        sys.exit(__doc__)
    opt = ["-o", "BatchMode=yes", "-o", "ConnectTimeout=10"] + (["-i", str(Path(a.key).expanduser())] if a.key else [])
    dest = a.dest.rstrip("/\\")
    local_tar = ROOT / "build" / ".sync.tar"
    local_tar.parent.mkdir(exist_ok=True)
    local_tar.write_bytes(pack())
    print(f"  scp -> {a.ssh}:{dest}/.sync.tar")
    subprocess.run(["scp", "-q", *opt, str(local_tar), f"{a.ssh}:{dest}/.sync.tar"], check=True)
    # hai lệnh riêng: chạy được cả trong PowerShell 5.1 (không có &&) lẫn sh
    r = subprocess.run(["ssh", *opt, a.ssh, f"tar -xf {dest}/.sync.tar -C {dest}"], capture_output=True, text=True)
    if r.returncode == 0:
        r = subprocess.run(["ssh", *opt, a.ssh, f"{a.python} {dest}/tools/tls_site.py --version"],
                           capture_output=True, text=True)
    local_tar.unlink()
    if r.returncode != 0:
        sys.exit(f"LỖI ở máy đích: {r.stderr.strip() or r.stdout.strip()}")
    remote = r.stdout.strip().splitlines()[-1]
    here = subprocess.run([sys.executable, str(ROOT / "tools" / "tls_site.py"), "--version"],
                          capture_output=True, text=True).stdout.strip()
    print(f"  máy đích: {remote}\n  máy này : {here}")
    if remote != here:
        sys.exit("KHÔNG KHỚP — kiểm tra lại")
    print("Đã cập nhật, mã băm khớp.")


if __name__ == "__main__":
    main()
