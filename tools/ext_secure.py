#!/usr/bin/env python3
"""PHẦN MỞ RỘNG E3 (ngoài yêu cầu đề) — đường postgres_fdw "kiểu production" khi các trạm ở các nơi khác nhau.

    python tools/ext_secure.py up        # make ext-secure        : bật E3
    python tools/ext_secure.py status    # make ext-secure-status : cấu hình + phiên TLS đang mở
    python tools/ext_secure.py test      # make ext-secure-test   : 6 phép thử (2 dương, 4 âm)
    python tools/ext_secure.py bench     # make ext-secure-bench  : chi phí TLS (0 / 30 ms) -> results/ext/e3_bench.csv
    python tools/ext_secure.py down      # make ext-secure-down   : trả về như `make link`

  Chế độ PRD (khoá riêng của trạm không rời khỏi trạm; xem tools/ext_secure_site.py):
    python tools/ext_secure.py ca-init           # make ext-secure-ca-init : tạo CA nội bộ (một lần)
    python tools/ext_secure.py sign [tệp.csr…]   # make ext-secure-sign    : CA ký CSR trong container không mạng
    python tools/ext_secure.py link              # make ext-secure-link    : trạm trung tâm dùng chứng chỉ đã cài

Bật E3 thì:
  1. PKI riêng của nhóm: một CA nội bộ (ECDSA P-256) ký chứng chỉ máy chủ cho từng trạm xa
     (SAN = <trạm>.<domain>, KHÔNG có IP) và chứng chỉ máy khách CN=fdw_reader cho trạm trung tâm.
     Tạo bằng openssl trong container trung tâm, chép về build/e3/ (không vào git), khoá CA không nằm trong trạm nào.
  2. Ở mỗi trạm xa (qua SQL, máy B không phải làm gì): đặt chứng chỉ vào thư mục dữ liệu, ssl = on, TLS ≥ 1.3;
     role fdw_reader chỉ có SELECT; pg_hba: fdw_reader CHỈ vào được bằng TLS + chứng chỉ máy khách (`cert`),
     mọi kết nối không mã hoá của fdw_reader bị từ chối.
  3. Ở trạm trung tâm: "DNS nội bộ" (giả lập bằng /etc/hosts của container) <trạm>.<domain> -> IP; srv_<trạm>
     dùng tên đó, sslmode=verify-full (kiểm tra CA + tên máy), sslnegotiation=direct; user mapping dùng
     fdw_reader + chứng chỉ máy khách — KHÔNG còn mật khẩu nào trong cấu hình fdw.
Không đổi lược đồ, dữ liệu, `make all`. `make link` (hay `ext-secure-down`) trả srv_* về như cũ.
Không bật cùng `ext-failover` hoặc `DELAY_MODE=proxy` (cả ba cùng sửa srv_*): lệnh `up` từ chối nếu srv_* đang bị sửa.
"""
import base64
import csv
import hashlib
import json
import os
import re
import secrets
import shutil
import statistics
import subprocess
import sys
from pathlib import Path

import delay
from common import RESULTS, ROOT, Config, die, docker_psql

PKI = ROOT / "build" / "e3"
ROLE = "fdw_reader"
HBA_BEGIN, HBA_END = "# >>> E3 ext-secure", "# <<< E3 ext-secure"
SUBDIR = "e3"          # thư mục con trong thư mục dữ liệu của mỗi trạm


def domain(cfg: Config) -> str:
    return cfg.secure.get("domain", "db.nhom8.internal")


def fqdn(cfg: Config, site: str) -> str:
    return f"{site}.{domain(cfg)}"


# ------------------------------------------------------------------ PKI
# ------------------------------------------------------------------ CA cho chế độ PRD
EXCHANGE = PKI / "exchange"
CA_EXT = {"server": "basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature\n"
                    "extendedKeyUsage=serverAuth\nsubjectAltName=DNS:{cn}\n",
          "client": "basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature\n"
                    "extendedKeyUsage=clientAuth\n"}


def ca_run(cfg: Config, script: str, check: bool = True) -> subprocess.CompletedProcess:
    """Mọi thao tác với khoá CA chạy trong một container DÙNG MỘT LẦN, KHÔNG CÓ MẠNG (--network none),
    chỉ gắn thư mục build/e3/. Khoá CA không bao giờ nằm trong container của trạm nào."""
    PKI.mkdir(parents=True, exist_ok=True)
    user = ["-u", f"{os.getuid()}:{os.getgid()}"] if hasattr(os, "getuid") else []
    r = subprocess.run(["docker", "run", "--rm", "--network", "none", *user, "-e", "HOME=/tmp",
                        "-v", f"{PKI.resolve()}:/ca", "-w", "/ca", cfg.image, "sh", "-c", script],
                       capture_output=True, text=True)
    if check and r.returncode != 0:
        die(f"CA: {r.stderr.strip() or r.stdout.strip()}")
    return r


def ca_init(cfg: Config):
    ec = "openssl genpkey -algorithm EC -pkeyopt ec_paramgen_curve:P-256 -out"
    if not (PKI / "ca.crt").exists():
        ca_run(cfg, f"""set -e; umask 077; {ec} ca.key
            openssl req -x509 -new -key ca.key -sha256 -days 1825 -subj '/O=Nhom 8 CS5104/CN=Nhom8 internal CA' \
              -addext 'basicConstraints=critical,CA:TRUE,pathlen:0' -addext 'keyUsage=critical,keyCertSign,cRLSign' \
              -out ca.crt; chmod 644 ca.crt""")
        print("  CA nội bộ MỚI: build/e3/ca.key (0600, chỉ ở máy A), build/e3/ca.crt")
    else:
        print("  CA nội bộ đã có — dùng lại")
    if not (PKI / "rogue_client.crt").exists():          # chỉ phục vụ phép thử âm T6
        ca_run(cfg, f"""set -e; umask 077; {ec} rogue_ca.key
            openssl req -x509 -new -key rogue_ca.key -days 30 -subj '/CN=rogue CA' -out rogue_ca.crt
            {ec} rogue_client.key
            openssl req -new -key rogue_client.key -subj '/CN={ROLE}' -out /tmp/r.csr
            printf 'extendedKeyUsage=clientAuth\n' > /tmp/r.ext
            openssl x509 -req -in /tmp/r.csr -CA rogue_ca.crt -CAkey rogue_ca.key -set_serial 1 -days 30 \
              -extfile /tmp/r.ext -out rogue_client.crt 2>/dev/null""")
    fp = ca_run(cfg, "openssl x509 -in ca.crt -noout -fingerprint -sha256").stdout.strip()
    print(f"  {fp}")
    EXCHANGE.mkdir(parents=True, exist_ok=True)
    shutil.copy(PKI / "ca.crt", EXCHANGE / "ca.crt")


def issue(cfg: Config, csr_rel: str, out_rel: str, profile: str, cn: str, days: int) -> dict:
    serial = secrets.token_hex(16)
    ext = CA_EXT[profile].format(cn=cn)
    ca_run(cfg, f"""set -e; printf '{ext}' > /tmp/p.ext
        openssl x509 -req -in {csr_rel} -CA ca.crt -CAkey ca.key -set_serial 0x{serial} -days {days} -sha256 \
          -extfile /tmp/p.ext -out {out_rel} 2>/dev/null; chmod 644 {out_rel}""")
    t = ca_run(cfg, f"openssl x509 -in {out_rel} -noout -enddate -fingerprint -sha256").stdout
    rec = {"serial": serial, "cn": cn, "profile": profile, "days": days,
           "not_after": re.search(r"notAfter=(.+)", t).group(1).strip(),
           "sha256": re.search(r"Fingerprint=([0-9A-F:]+)", t).group(1)}
    with open(PKI / "issued.jsonl", "a", encoding="utf-8") as f:         # nhật ký cấp phát (kiểm toán, thu hồi)
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def sign(cfg: Config, files: list[str]):
    """Ký CSR theo CHÍNH SÁCH của CA: chỉ CN = <trạm xa>.<domain> (máy chủ) hoặc fdw_reader (máy khách).
    CA tự đặt SAN/EKU/hạn — không chép phần mở rộng từ CSR."""
    if not (PKI / "ca.key").exists():
        die("chưa có CA — chạy make ext-secure-ca-init")
    csrs = [Path(f) for f in files] or sorted(EXCHANGE.glob("*.csr"))
    if not csrs:
        die(f"không có tệp .csr nào trong {EXCHANGE.relative_to(ROOT)}")
    days = int(cfg.secure.get("cert_days", 90))
    allowed = {fqdn(cfg, s): "server" for s in cfg.remote_sites()} | {ROLE: "client"}
    EXCHANGE.mkdir(parents=True, exist_ok=True)
    for f in csrs:
        f = f if f.is_absolute() else (Path.cwd() / f)
        if f.parent.resolve() != EXCHANGE.resolve():
            shutil.copy(f, EXCHANGE / f.name)
        rel = f"exchange/{f.name}"
        fp = hashlib.sha256(f.read_bytes().replace(b"\r\n", b"\n")).hexdigest()[:16]
        if ca_run(cfg, f"openssl req -in {rel} -noout -verify", check=False).returncode != 0:
            die(f"{f.name}: chữ ký CSR không hợp lệ (tệp hỏng hoặc bị sửa)")
        subj = ca_run(cfg, f"openssl req -in {rel} -noout -subject").stdout
        m = re.search(r"CN\s*=\s*([^,/\n]+)", subj)
        cn = m.group(1).strip() if m else ""
        if cn not in allowed:
            die(f"{f.name}: TỪ CHỐI ký — CN '{cn}' không thuộc chính sách ({', '.join(allowed)})")
        rec = issue(cfg, rel, f"exchange/{f.stem}.crt", allowed[cn], cn, days)
        print(f"  ký {f.name:<18} sha256 CSR {fp}…  CN={cn} ({allowed[cn]}) · {days} ngày · tới {rec['not_after']}"
              f"\n      -> build/e3/exchange/{f.stem}.crt  serial {rec['serial'][:12]}…")
    shutil.copy(PKI / "ca.crt", EXCHANGE / "ca.crt")
    print("Gửi <tên>.crt + ca.crt về máy chứa trạm (build/e3/exchange/) rồi chạy make ext-secure-site-install ở đó.")


def test_client(cfg: Config) -> tuple[str, str]:
    """Chứng chỉ máy khách NGẮN HẠN (1 ngày) cho người vận hành chạy phép thử từ máy A."""
    ca_init(cfg) if not (PKI / "ca.crt").exists() else None
    ca_run(cfg, f"""set -e; umask 077
        openssl genpkey -algorithm EC -pkeyopt ec_paramgen_curve:P-256 -out test_client.key
        openssl req -new -key test_client.key -subj '/CN={ROLE}' -out /tmp/t.csr; cp /tmp/t.csr test_client.csr""")
    issue(cfg, "test_client.csr", "test_client.crt", "client", ROLE, 1)
    (PKI / "test_client.csr").unlink()
    (PKI / "test_client.key").chmod(0o600)
    return str(PKI / "test_client.crt"), str(PKI / "test_client.key")


def link_prd(cfg: Config):
    """Chế độ PRD: trạm xa đã tự cài TLS (ext_secure_site install), trạm trung tâm đã có chứng chỉ máy khách."""
    guard(cfg)
    c = cfg.container(cfg.central)
    with cfg.connect(cfg.central) as k:
        d = f"{data_dir(k)}/{SUBDIR}"
    r = subprocess.run(["docker", "exec", "-u", "postgres", c, "sh", "-c",
                        f"test -f {d}/{ROLE}.crt && test -f {d}/{ROLE}.key && test -f {d}/ca.crt"])
    if r.returncode != 0:
        die(f"trạm trung tâm chưa có chứng chỉ máy khách — chạy ở máy {cfg.machine_of(cfg.central)}: "
            "make ext-secure-site-csr CLIENT=1 → ext-secure-sign → ext-secure-site-install CLIENT=1")
    for l in set_hosts(cfg, True):
        print(f"  /etc/hosts: {l}")
    link_mode(cfg, "tls_direct")
    with cfg.connect(cfg.central) as k:
        for s in cfg.remote_sites():
            try:
                n = k.execute(f"SELECT count(*) FROM s_{s}.hotel").fetchone()[0]
                print(f"  srv_{s} -> {fqdn(cfg, s)} (verify-full, direct TLS, {ROLE} + cert): {n} khách sạn ✓")
            except Exception as e:  # noqa: BLE001
                link_mode(cfg, "plain")
                set_hosts(cfg, False)
                die(f"srv_{s} chưa nối được bằng TLS ({str(e).strip().splitlines()[0]}) — đã trả srv_* về như cũ. "
                    f"Trạm {s} (máy {cfg.machine_of(s)}) đã chạy ext-secure-site-install chưa?")
    print("E3 (PRD) BẬT. Kiểm tra: make ext-secure-test · make check")


def make_pki(cfg: Config):
    """Tạo CA + chứng chỉ (một lần; chạy lại thì dùng lại để chứng chỉ không đổi)."""
    if (PKI / "ca.crt").exists():
        print(f"  PKI đã có ở {PKI.relative_to(ROOT)} — dùng lại")
        return
    ec = "openssl ecparam -name prime256v1 -genkey -noout -out"
    lines = ["set -e", "rm -rf /tmp/e3pki", "mkdir -p /tmp/e3pki", "cd /tmp/e3pki",
             f"{ec} ca.key",
             "openssl req -x509 -new -key ca.key -sha256 -days 825 -subj '/O=Nhom 8 CS5104/CN=Nhom8 internal CA' "
             "-addext 'basicConstraints=critical,CA:TRUE' -addext 'keyUsage=critical,keyCertSign,cRLSign' -out ca.crt"]

    def leaf(name, cn, ext, ca="ca"):
        lines.extend([f"{ec} {name}.key",
                      f"openssl req -new -key {name}.key -subj '/O=Nhom 8 CS5104/CN={cn}' -out {name}.csr",
                      f"printf '{ext}' > {name}.ext",
                      f"openssl x509 -req -in {name}.csr -CA {ca}.crt -CAkey {ca}.key -CAcreateserial -days 825 "
                      f"-sha256 -extfile {name}.ext -out {name}.crt"])
    for s in cfg.remote_sites():
        leaf(s, fqdn(cfg, s), f"subjectAltName=DNS:{fqdn(cfg, s)}\\nextendedKeyUsage=serverAuth\\n"
                              "keyUsage=critical,digitalSignature")
    leaf(ROLE, ROLE, "extendedKeyUsage=clientAuth\\nkeyUsage=critical,digitalSignature")
    # chứng chỉ "giả": CN=fdw_reader nhưng do một CA lạ ký — dùng cho phép thử âm
    lines += [f"{ec} rogue_ca.key",
              "openssl req -x509 -new -key rogue_ca.key -sha256 -days 30 -subj '/CN=rogue CA' "
              "-addext 'basicConstraints=critical,CA:TRUE' -out rogue_ca.crt"]
    leaf("rogue_client", ROLE, "extendedKeyUsage=clientAuth", ca="rogue_ca")
    lines += ["rm -f *.csr *.ext *.srl"]
    c = cfg.container(cfg.central)
    r = subprocess.run(["docker", "exec", "-u", "postgres", c, "sh", "-c", "\n".join(lines)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        die(f"openssl lỗi: {r.stderr.strip()}")
    PKI.parent.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(PKI, ignore_errors=True)
    subprocess.run(["docker", "cp", f"{c}:/tmp/e3pki", str(PKI)], check=True, capture_output=True)
    subprocess.run(["docker", "exec", c, "rm", "-rf", "/tmp/e3pki"], check=True)
    for k in PKI.glob("*.key"):
        k.chmod(0o600)
    print(f"  PKI mới: CA nội bộ + {len(cfg.remote_sites())} chứng chỉ máy chủ + chứng chỉ máy khách {ROLE} "
          f"-> {PKI.relative_to(ROOT)}/ (khoá CA chỉ nằm ở đây)")


# ------------------------------------------------------------------ ghi tệp vào trạm qua SQL
def put_file(conn, path: str, data: bytes, mode: str = "600"):
    """Ghi tệp vào container của trạm bằng COPY … TO PROGRAM (superuser) — không cần vào máy B."""
    b64 = base64.b64encode(data).decode()
    d = path.rsplit("/", 1)[0]
    conn.execute(f"COPY (SELECT 1) TO PROGRAM 'mkdir -p {d} && echo {b64} | base64 -d > {path} && chmod {mode} {path}'")


def data_dir(conn) -> str:
    return conn.execute("SHOW data_directory").fetchone()[0]


def set_hba(conn, block: str | None):
    hba = conn.execute("SHOW hba_file").fetchone()[0]
    text = conn.execute("SELECT pg_read_file(%s)", [hba]).fetchone()[0]
    if HBA_BEGIN in text:
        a, b = text.index(HBA_BEGIN), text.index(HBA_END) + len(HBA_END) + 1
        text = text[:a] + text[b:]
    if block:
        text = f"{HBA_BEGIN}\n{block}\n{HBA_END}\n" + text      # đặt ĐẦU tệp: pg_hba khớp dòng đầu tiên
    put_file(conn, hba, text.encode(), "600")
    conn.execute("SELECT pg_reload_conf()")
    bad = conn.execute("SELECT line_number, error FROM pg_hba_file_rules WHERE error IS NOT NULL").fetchall()
    if bad:
        die(f"pg_hba lỗi: {bad}")


# ------------------------------------------------------------------ trạm xa
def secure_site(cfg: Config, s: str):
    with cfg.connect(s) as c:
        d = f"{data_dir(c)}/{SUBDIR}"
        put_file(c, f"{d}/server.crt", (PKI / f"{s}.crt").read_bytes(), "644")
        put_file(c, f"{d}/server.key", (PKI / f"{s}.key").read_bytes(), "600")
        put_file(c, f"{d}/ca.crt", (PKI / "ca.crt").read_bytes(), "644")
        for k, v in [("ssl_cert_file", f"{d}/server.crt"), ("ssl_key_file", f"{d}/server.key"),
                     ("ssl_ca_file", f"{d}/ca.crt"), ("ssl_min_protocol_version", "TLSv1.3"), ("ssl", "on")]:
            c.execute(f"ALTER SYSTEM SET {k} = '{v}'")
        c.execute("SELECT pg_reload_conf()")
        # quyền tối thiểu: chỉ đọc
        if not c.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", [ROLE]).fetchone():
            c.execute(f"CREATE ROLE {ROLE} LOGIN")
        c.execute(f"GRANT CONNECT ON DATABASE {cfg.db} TO {ROLE}")
        c.execute(f"GRANT USAGE ON SCHEMA public TO {ROLE}")
        c.execute(f"GRANT SELECT ON ALL TABLES IN SCHEMA public TO {ROLE}")
        c.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO {ROLE}")
        set_hba(c, f"hostssl   {cfg.db}  {ROLE}  all  cert\n"
                   f"hostnossl all    {ROLE}  all  reject\n"
                   f"hostssl   all    {ROLE}  all  reject")
        ssl = c.execute("SELECT setting FROM pg_settings WHERE name = 'ssl'").fetchone()[0]
    print(f"  {s:<9} TLS {ssl}, ≥ TLSv1.3, chứng chỉ {fqdn(cfg, s)}; role {ROLE} (chỉ SELECT); pg_hba: {ROLE} chỉ qua TLS + cert")


def unsecure_site(cfg: Config, s: str):
    with cfg.connect(s) as c:
        set_hba(c, None)
        for k in ("ssl", "ssl_cert_file", "ssl_key_file", "ssl_ca_file", "ssl_min_protocol_version"):
            c.execute(f"ALTER SYSTEM RESET {k}")
        c.execute("SELECT pg_reload_conf()")
        if c.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", [ROLE]).fetchone():
            c.execute(f"DROP OWNED BY {ROLE}")
            c.execute(f"DROP ROLE {ROLE}")
        d = f"{data_dir(c)}/{SUBDIR}"        # giữ backup/ của chế độ PRD
        c.execute(f"COPY (SELECT 1) TO PROGRAM 'cd {d} 2>/dev/null && rm -rf server.key server.crt ca.crt pending prev || true'")
    print(f"  {s:<9} TLS tắt, xoá role {ROLE}, gỡ dòng pg_hba của E3")


# ------------------------------------------------------------------ trạm trung tâm
def opts_of(c, sql: str, args) -> dict:
    row = c.execute(sql, args).fetchone()
    return dict(o.split("=", 1) for o in (row[0] or [])) if row else {}


def alter(c, target: str, cur: dict, want: dict):
    """want: tên -> giá trị (None = bỏ). Sinh ADD/SET/DROP đúng với tuỳ chọn đang có."""
    acts = []
    for k, v in want.items():
        if v is None:
            if k in cur:
                acts.append(f"DROP {k}")
        else:
            acts.append(f"{'SET' if k in cur else 'ADD'} {k} '{v}'")
    if acts:
        c.execute(f"ALTER {target} OPTIONS ({', '.join(acts)})")


def server_opts(c, s):
    return opts_of(c, "SELECT srvoptions FROM pg_foreign_server WHERE srvname = %s", [f"srv_{s}"])


def mapping_opts(c, s):
    return opts_of(c, "SELECT umoptions FROM pg_user_mappings WHERE srvname = %s", [f"srv_{s}"])


def set_hosts(cfg: Config, on: bool):
    """DNS nội bộ giả lập: /etc/hosts của container trung tâm. Bản thật: một vùng DNS riêng (vd. Route 53 private zone)."""
    lines = []
    if on:
        ips = delay.target_ips(cfg)          # IP mà container trung tâm thực sự dùng để tới từng trạm
        lines = [f"{ips[s]} {fqdn(cfg, s)}" for s in cfg.remote_sites()]
    script = (f"grep -v '{domain(cfg)}' /etc/hosts > /tmp/hosts.e3; "
              + "".join(f"echo '{l}' >> /tmp/hosts.e3; " for l in lines)
              + "cat /tmp/hosts.e3 > /etc/hosts; rm /tmp/hosts.e3")
    subprocess.run(["docker", "exec", "-u", "root", cfg.container(cfg.central), "sh", "-c", script], check=True)
    return lines


def link_mode(cfg: Config, mode: str):
    """mode: plain (như make link) | tls (verify-full + cert, thương lượng kiểu cũ) | tls_direct (PG ≥ 17: bỏ SSLRequest)."""
    with cfg.connect(cfg.central) as c:
        d = f"{data_dir(c)}/{SUBDIR}"
        for s in cfg.remote_sites():
            host, port = cfg.docker_addr(s)
            if mode == "plain":
                srv = {"host": host, "port": str(port), "sslmode": None, "sslrootcert": None, "sslnegotiation": None}
                um = {"user": cfg.user, "password": cfg.password, "sslcert": None, "sslkey": None}
            else:
                srv = {"host": fqdn(cfg, s), "port": str(port), "sslmode": "verify-full", "sslrootcert": f"{d}/ca.crt",
                       "sslnegotiation": "direct" if mode == "tls_direct" else None}
                um = {"user": ROLE, "password": None, "sslcert": f"{d}/{ROLE}.crt", "sslkey": f"{d}/{ROLE}.key"}
            alter(c, f"SERVER srv_{s}", server_opts(c, s), srv)
            alter(c, f"USER MAPPING FOR {cfg.user} SERVER srv_{s}", mapping_opts(c, s), um)


def guard(cfg: Config):
    """Không chồng lên ext-failover / DELAY_MODE=proxy: srv_* phải đang trỏ đúng trạm (tên E3 hoặc địa chỉ gốc)."""
    with cfg.connect(cfg.central) as c:
        for s in cfg.remote_sites():
            o = server_opts(c, s)
            if not o:
                die("chưa có srv_* — chạy make link trước")
            if o.get("host") not in (cfg.docker_addr(s)[0], fqdn(cfg, s)) or o.get("port") != str(cfg.docker_addr(s)[1]):
                die(f"srv_{s} đang trỏ {o.get('host')}:{o.get('port')} (ext-failover hoặc DELAY_MODE=proxy đang bật?) "
                    "— tắt chúng trước")


# ------------------------------------------------------------------ lệnh
def up(cfg: Config):
    guard(cfg)
    print("E3 · 1/3 PKI nội bộ")
    make_pki(cfg)
    print("E3 · 2/3 trạm xa: TLS, role chỉ đọc, pg_hba")
    for s in cfg.remote_sites():
        secure_site(cfg, s)
    print(f"E3 · 3/3 trạm trung tâm {cfg.central}: DNS nội bộ, chứng chỉ máy khách, srv_* verify-full")
    with cfg.connect(cfg.central) as c:
        d = f"{data_dir(c)}/{SUBDIR}"
        put_file(c, f"{d}/ca.crt", (PKI / "ca.crt").read_bytes(), "644")
        put_file(c, f"{d}/{ROLE}.crt", (PKI / f"{ROLE}.crt").read_bytes(), "644")
        put_file(c, f"{d}/{ROLE}.key", (PKI / f"{ROLE}.key").read_bytes(), "600")
    for l in set_hosts(cfg, True):
        print(f"  /etc/hosts: {l}")
    link_mode(cfg, "tls_direct")
    with cfg.connect(cfg.central) as c:
        for s in cfg.remote_sites():
            n = c.execute(f"SELECT count(*) FROM s_{s}.hotel").fetchone()[0]
            print(f"  srv_{s} -> {fqdn(cfg, s)} (verify-full, direct TLS, user {ROLE} + cert): {n} khách sạn ✓")
    print("E3 BẬT. Kiểm tra: make ext-secure-test · make check · make q   (tắt: make ext-secure-down)")


def down(cfg: Config):
    link_mode(cfg, "plain")
    set_hosts(cfg, False)
    with cfg.connect(cfg.central) as c:
        c.execute(f"COPY (SELECT 1) TO PROGRAM 'rm -rf {data_dir(c)}/{SUBDIR}'")
    for s in cfg.remote_sites():
        unsecure_site(cfg, s)
    print("E3 TẮT: srv_* trở lại như make link (PKI vẫn giữ ở build/e3/ để bật lại).")


def status(cfg: Config):
    with cfg.connect(cfg.central) as c:
        for s in cfg.remote_sites():
            so, uo = server_opts(c, s), mapping_opts(c, s)
            print(f"  srv_{s:<9} host={so.get('host')} sslmode={so.get('sslmode', '-')} "
                  f"sslnegotiation={so.get('sslnegotiation', '-')} user={uo.get('user')} "
                  f"password={'CÓ' if 'password' in uo else 'không'} sslcert={'CÓ' if 'sslcert' in uo else 'không'}")
        for s in cfg.remote_sites():                       # mở phiên fdw rồi xem nó từ phía trạm xa
            c.execute(f"SELECT count(*) FROM s_{s}.room_type")
        pid_app = "postgres_fdw"
        for s in cfg.remote_sites():
            with cfg.connect(s) as r:
                rows = r.execute("SELECT a.usename, s.ssl, s.version, s.cipher, s.client_dn "
                                 "FROM pg_stat_ssl s JOIN pg_stat_activity a USING (pid) "
                                 "WHERE a.application_name = %s", [pid_app]).fetchall()
            for u, ssl, ver, ciph, dn in rows:
                print(f"  phiên fdw tại {s:<9}: user={u} ssl={ssl} {ver or ''} {ciph or ''} client_dn={dn or '-'}")


def try_conn(cfg: Config, s: str, **kw) -> str:
    import psycopg
    host, port = cfg.host_addr(s)
    params = dict(host=host, port=port, dbname=cfg.db, user=ROLE, connect_timeout=5) | kw
    try:
        with psycopg.connect(**params) as c:
            v = c.execute("SELECT version FROM pg_stat_ssl WHERE pid = pg_backend_pid()").fetchone()[0]
            return f"OK ({v})"
    except Exception as e:  # noqa: BLE001
        msg = str(e).strip().splitlines()[0]
        return "TỪ CHỐI: " + (msg.split(" failed: ", 2)[-1] if " failed: " in msg else msg)[:220]


def test(cfg: Config):
    """Thử từ máy A tới trạm xa ở máy B (đi qua mạng thật)."""
    import psycopg
    s = next((x for x in cfg.remote_sites() if cfg.machine_of(x) != cfg.machine_of(cfg.central)), cfg.remote_sites()[0])
    ip, port = cfg.host_addr(s)
    name = fqdn(cfg, s)
    ca = str(PKI / "ca.crt")
    crt, key = test_client(cfg)          # chứng chỉ 1 ngày do CA cấp riêng cho phép thử
    good = dict(host=name, hostaddr=ip, sslmode="verify-full", sslrootcert=ca, sslcert=crt, sslkey=key)
    cases = [
        ("T1 đủ: tên đúng + CA nội bộ + chứng chỉ máy khách", True, good),
        ("T2 đủ, direct TLS (PG ≥ 17, bỏ một vòng SSLRequest)", True, good | {"sslnegotiation": "direct"}),
        ("T3 không mã hoá (sslmode=disable)", False, dict(sslmode="disable")),
        ("T4 gọi bằng IP, không bằng tên (verify-full)", False, dict(host=ip, sslmode="verify-full", sslrootcert=ca,
                                                                      sslcert=crt, sslkey=key)),
        ("T5 TLS nhưng không có chứng chỉ máy khách", False, dict(host=name, hostaddr=ip, sslmode="verify-full",
                                                                   sslrootcert=ca, sslcert="", sslkey="")),
        ("T6 chứng chỉ CN=fdw_reader do CA lạ ký", False, good | {"sslcert": str(PKI / "rogue_client.crt"),
                                                                    "sslkey": str(PKI / "rogue_client.key")}),
    ]
    print(f"Thử tới {cfg.label(s)} với user {ROLE}:")
    passed = 0
    for title, expect_ok, kw in cases:
        r = try_conn(cfg, s, **kw)
        ok = r.startswith("OK") == expect_ok
        passed += ok
        print(f"  [{'ĐẠT' if ok else 'SAI'}] {title}: {r}")
    # T7: đúng hết nhưng thử GHI -> bị từ chối (quyền tối thiểu)
    host, port = cfg.host_addr(s)
    try:
        with psycopg.connect(host=name, hostaddr=ip, port=port, dbname=cfg.db, user=ROLE, sslmode="verify-full",
                             sslrootcert=ca, sslcert=crt, sslkey=key, connect_timeout=5) as c:
            c.execute("UPDATE room_type SET capacity = capacity WHERE false")
            r, ok = "GHI ĐƯỢC (sai)", False
    except Exception as e:  # noqa: BLE001
        r, ok = "TỪ CHỐI: " + str(e).strip().splitlines()[0][:120], "permission denied" in str(e)
    passed += ok
    print(f"  [{'ĐẠT' if ok else 'SAI'}] T7 {ROLE} thử UPDATE: {r}")
    total = len(cases) + 1
    print(f"KẾT QUẢ: {passed}/{total} ĐẠT")
    (RESULTS / "ext").mkdir(parents=True, exist_ok=True)
    if passed != total:
        sys.exit(1)


def bench(cfg: Config):
    """Chi phí TLS: thời gian MỞ kết nối fdw (lần chạy đầu mỗi phiên) và thời gian Q2 khi kết nối đã mở."""
    from bench import timed_runs
    guard(cfg)
    if not is_on(cfg):
        die("E3 chưa bật — chạy make ext-secure trước")
    q2 = (ROOT / "sql" / "queries" / "q2.sql").read_text(encoding="utf-8")
    remote = [s for s in cfg.remote_sites() if cfg.machine_of(s) != cfg.machine_of(cfg.central)][0]
    probe = f"SELECT capacity FROM s_{remote}.room_type WHERE room_type_code = 'RT01'"
    rows = []
    try:
        for d in (0, cfg.delay_ms):
            delay.on(cfg) if d else delay.off(cfg)
            for mode in ("plain", "tls", "tls_direct"):
                link_mode(cfg, mode)
                conn_ms, steady = [], []
                for _ in range(9):                      # 9 phiên mới, mỗi phiên: lần 1 có mở kết nối, lần 2..5 không
                    t = timed_runs(cfg, cfg.central, probe)
                    conn_ms.append(t[0] - statistics.median(t[1:]))
                    steady.append(statistics.median(t[1:]))
                q = timed_runs(cfg, cfg.central, q2)
                r = {"delay_ms": d, "mode": mode, "connect_extra_ms": round(statistics.median(conn_ms), 2),
                     "probe_steady_ms": round(statistics.median(steady), 2),
                     "q2_first_ms": round(q[0], 2), "q2_median_ms": round(statistics.median(q[1:]), 2)}
                rows.append(r)
                print(f"  trễ {d:>2} ms  {mode:<10}  mở kết nối +{r['connect_extra_ms']:>7.2f} ms   "
                      f"truy vấn nhỏ {r['probe_steady_ms']:>7.2f} ms   Q2 lần đầu {r['q2_first_ms']:>8.2f} / "
                      f"trung vị {r['q2_median_ms']:>7.2f} ms", flush=True)
    finally:
        delay.off(cfg)
        link_mode(cfg, "tls_direct")          # trả về trạng thái E3 bật
    out = RESULTS / "ext" / "e3_bench.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"-> {out.relative_to(ROOT)}")


def is_on(cfg: Config) -> bool:
    """E3 đã bật ở các trạm xa chưa (có role fdw_reader + dòng pg_hba)."""
    with cfg.connect(cfg.remote_sites()[0]) as c:
        return bool(c.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", [ROLE]).fetchone())


def main():
    cfg = Config()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "sign":
        return sign(cfg, sys.argv[2:])
    {"up": up, "down": down, "status": status, "test": test, "bench": bench, "ca-init": ca_init,
     "link": link_prd}.get(cmd, lambda _: die(__doc__))(cfg)


if __name__ == "__main__":
    main()
