"""Phần dùng chung: đọc deploy.toml, tên container, địa chỉ kết nối từng trạm.

Chỉ dùng thư viện chuẩn ở mức module (deploy.py chạy được trên máy B mà không cần venv);
psycopg chỉ được import bên trong hàm connect().
"""
from __future__ import annotations

import os
import subprocess
import sys
import tomllib
from pathlib import Path

# Windows: console/pipe mặc định cp1252 không in được tiếng Việt
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

ROOT = Path(__file__).resolve().parent.parent
SQL_DIR = ROOT / "sql"
RESULTS = ROOT / "results"
GEN = ROOT / "datagen" / "de06_hotel" / "generate.py"

SITES_ORDER = ["dalat", "nhatrang", "phuquoc", "danang"]
# Thứ tự nạp theo khoá ngoại (cha trước con)
ALL_TABLES = ["room_type", "tour_group", "hotel", "room", "booking",
              "req_tour", "req_business", "req_family", "req_family_child"]
REPLICATED = ["room_type", "tour_group"]                     # sao chép ra mọi trạm
FRAGMENTED = [t for t in ALL_TABLES if t not in REPLICATED]  # bị chia -> có all_<bảng>
PK = {"room_type": ["room_type_code"], "tour_group": ["tour_group_id"], "hotel": ["hotel_id"],
      "room": ["room_id"], "booking": ["booking_id"], "req_tour": ["booking_id"],
      "req_business": ["booking_id"], "req_family": ["booking_id"],
      "req_family_child": ["booking_id", "seq"]}
ID_BLOCK = 10_000_000          # dải khoá chính cho dòng mới của mỗi trạm
TOUR_GROUP_NEW_START = 100_001  # đoàn tour mới (sequence ở trạm trung tâm)


class Config:
    def __init__(self, path: str | None = None):
        path = path or os.environ.get("DEPLOY", "deploy.toml")
        p = Path(path)
        if not p.is_absolute():
            p = ROOT / p
        with open(p, "rb") as f:
            raw = tomllib.load(f)
        self.path = p
        self.project = raw["project"]
        self.machines = raw["machines"]
        self.sites = raw["sites"]
        self.ref = raw["ref"]
        # PHẦN MỞ RỘNG (ngoài yêu cầu đề): bản sao dự phòng [ext.replica.<trạm>], chỉ make ext-* dùng tới
        self.replicas = {f"{s}_replica": dict(v, of=s)
                         for s, v in raw.get("ext", {}).get("replica", {}).items()}
        self.secure = raw.get("ext", {}).get("secure", {})         # E3: [ext.secure]
        self.here = os.environ.get("MACHINE", "A")
        self.central = self.project["central"]
        self.db = self.project["db"]
        self.user = self.project["user"]
        self.password = self.project["password"]
        self.image = self.project["image"]
        self.delay_ms = int(self.project.get("delay_ms", 30))
        self.size = os.environ.get("SIZE") or self.project.get("data_size", "lab")

    # ---- nút = một trạm hoặc ref
    def nodes(self):
        return list(self.sites) + ["ref"]

    def node(self, name: str) -> dict:
        if name == "ref":
            return self.ref
        return self.replicas[name] if name in self.replicas else self.sites[name]

    def machine_of(self, name: str) -> str:
        return self.node(name)["machine"]

    def nodes_on(self, machine: str):
        return [n for n in self.nodes() if self.machine_of(n) == machine]

    def remote_sites(self):
        return [s for s in self.sites if s != self.central]

    @staticmethod
    def container(name: str) -> str:
        return f"cs5104_{name}"

    def volume(self, name: str) -> str:
        return f"cs5104_{name}_data"

    def machine_ip(self, name: str) -> str:
        return self.machines[self.machine_of(name)]["ip"]

    # ---- địa chỉ nhìn từ chương trình chạy trên máy chủ (giao diện, dashboard, nạp dữ liệu)
    def host_addr(self, name: str) -> tuple[str, int]:
        if self.machine_of(name) == self.here:
            return "127.0.0.1", int(self.node(name)["port"])
        return self.machine_ip(name), int(self.node(name)["port"])

    # ---- địa chỉ nhìn từ container trạm trung tâm (postgres_fdw)
    def docker_addr(self, name: str, from_node: str | None = None) -> tuple[str, int]:
        from_node = from_node or self.central
        if self.machine_of(name) == self.machine_of(from_node):
            return self.container(name), 5432          # cùng máy: đi qua mạng Docker nội bộ
        m = self.machines[self.machine_of(name)]
        return m.get("docker_ip", m["ip"]), int(self.node(name)["port"])

    def conninfo(self, name: str, timeout: int = 3) -> str:
        host, port = self.host_addr(name)
        return (f"host={host} port={port} dbname={self.db} user={self.user} "
                f"password={self.password} connect_timeout={timeout} application_name=cs5104_tools")

    def connect(self, name: str, timeout: int = 3, autocommit: bool = True):
        import psycopg
        return psycopg.connect(self.conninfo(name, timeout), autocommit=autocommit)

    def label(self, name: str) -> str:
        m = self.machine_of(name)
        host, port = self.machine_ip(name), self.node(name)["port"]
        return f"{name} @ máy {m} ({self.machines[m]['os']}, {host}:{port})"


def run(cmd: list[str], check: bool = True, capture: bool = False, **kw) -> subprocess.CompletedProcess:
    if not capture:
        print("  $", " ".join(cmd), flush=True)
    return subprocess.run(cmd, check=check, text=True,
                          capture_output=capture, **kw)


def docker_psql(cfg: Config, name: str, sql: str | None = None, files: list[str] | None = None,
                args: list[str] | None = None) -> str:
    """Chạy psql ngay trong container (qua unix socket — không có độ trễ mạng client↔trạm)."""
    cmd = ["docker", "exec", "-i", cfg.container(name), "psql", "-U", cfg.user, "-d", cfg.db,
           "-X", "-v", "ON_ERROR_STOP=1"] + (args or [])
    stdin = None
    if sql is not None:
        stdin = sql
    elif files:
        stdin = "\n".join(Path(f).read_text(encoding="utf-8") for f in files)
    r = subprocess.run(cmd, input=stdin, text=True, capture_output=True, encoding="utf-8")
    if r.returncode != 0:
        raise RuntimeError(f"psql@{name} lỗi:\n{r.stderr}")
    return r.stdout


def ok(msg: str):
    print(f"  [OK]   {msg}", flush=True)


def fail(msg: str):
    print(f"  [FAIL] {msg}", flush=True)


def die(msg: str, code: int = 1):
    print(f"LỖI: {msg}", file=sys.stderr)
    sys.exit(code)
