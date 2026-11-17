#!/usr/bin/env python3
"""E3 — bảo mật đường truyền, MẶC ĐỊNH của hệ. Chạy ở máy A.

    python tools/tls.py secure          # make secure (nằm trong make all): CA + chứng chỉ cho MỌI nút, chạy lại được
    python tools/tls.py status          # make tls-status : chứng chỉ từng nút, cấu hình srv_*, phiên fdw đang mở
    python tools/tls.py test            # make tls-test   : 8 phép thử (2 dương, 6 âm)
    python tools/tls.py ca-init         # make tls-ca-init: tạo CA nội bộ (secure tự gọi)
    python tools/tls.py sign [tệp.csr…] # make tls-sign   : ký CSR (chế độ chặt: CSR do từng máy tự gửi tới)
    python tools/tls.py off             # make tls-off    : tạm TẮT TLS toàn hệ (gỡ lỗi); `make secure` bật lại

`secure` với mỗi nút (dalat, nhatrang, phuquoc, danang, ref): nếu chưa có chứng chỉ hợp lệ của CA hiện tại hoặc còn
< 30 ngày => sinh khoá + CSR TRONG container của nút (nút ở máy B: qua kênh quản trị SQL, khoá vẫn không rời container)
→ CA ký trong container dùng một lần không có mạng → cài có kiểm tra, sao lưu, tự hoàn tác (tools/tls_site.py).
Thêm chứng chỉ máy khách fdw_reader cho trạm trung tâm. Sau đó `make link` dựng postgres_fdw qua TLS verify-full.
"""
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import time
from pathlib import Path

import tls_site
from common import PKI, RESULTS, ROOT, TLS_OFF_MARK, Config, die
from tls_site import ROLE, SUBDIR

EXCHANGE = PKI / "exchange"
CA_EXT = {"server": "basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature\n"
                    "extendedKeyUsage=serverAuth\nsubjectAltName=DNS:{cn}\n",
          "client": "basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature\n"
                    "extendedKeyUsage=clientAuth\n"}


# ------------------------------------------------------------------ CA
def ca_run(cfg: Config, script: str, check: bool = True) -> subprocess.CompletedProcess:
    """Mọi thao tác với khoá CA chạy trong một container DÙNG MỘT LẦN, KHÔNG CÓ MẠNG (--network none),
    chỉ gắn thư mục build/e3/. Khoá CA không bao giờ nằm trong container của nút nào."""
    PKI.mkdir(parents=True, exist_ok=True)
    user = ["-u", f"{os.getuid()}:{os.getgid()}"] if hasattr(os, "getuid") else []
    r = subprocess.run(["docker", "run", "--rm", "--network", "none", *user, "-e", "HOME=/tmp",
                        "-v", f"{PKI.resolve()}:/ca", "-w", "/ca", cfg.image, "sh", "-c", script],
                       capture_output=True, text=True)
    if check and r.returncode != 0:
        die(f"CA: {r.stderr.strip() or r.stdout.strip()}")
    return r


def ca_init(cfg: Config, quiet: bool = False):
    ec = "openssl genpkey -algorithm EC -pkeyopt ec_paramgen_curve:P-256 -out"
    if not (PKI / "ca.crt").exists():
        ca_run(cfg, f"""set -e; umask 077; {ec} ca.key
            openssl req -x509 -new -key ca.key -sha256 -days 1825 -subj '/O=Nhom 8 CS5104/CN=Nhom8 internal CA' \\
              -addext 'basicConstraints=critical,CA:TRUE,pathlen:0' -addext 'keyUsage=critical,keyCertSign,cRLSign' \\
              -out ca.crt; chmod 644 ca.crt""")
        print("  CA nội bộ MỚI: build/e3/ca.key (0600, chỉ ở máy A), build/e3/ca.crt")
    elif not quiet:
        print("  CA nội bộ đã có — dùng lại")
    if not (PKI / "rogue_client.crt").exists():          # chỉ phục vụ phép thử âm T6
        ca_run(cfg, f"""set -e; umask 077; {ec} rogue_ca.key
            openssl req -x509 -new -key rogue_ca.key -days 3650 -subj '/CN=rogue CA' -out rogue_ca.crt
            {ec} rogue_client.key
            openssl req -new -key rogue_client.key -subj '/CN={ROLE}' -out /tmp/r.csr
            printf 'extendedKeyUsage=clientAuth\\n' > /tmp/r.ext
            openssl x509 -req -in /tmp/r.csr -CA rogue_ca.crt -CAkey rogue_ca.key -set_serial 1 -days 3650 \\
              -extfile /tmp/r.ext -out rogue_client.crt 2>/dev/null""")
    fp = ca_run(cfg, "openssl x509 -in ca.crt -noout -fingerprint -sha256").stdout.strip()
    print(f"  CA {fp.split('=')[1][:29]}…")
    EXCHANGE.mkdir(parents=True, exist_ok=True)
    shutil.copy(PKI / "ca.crt", EXCHANGE / "ca.crt")


def issue(cfg: Config, csr_rel: str, out_rel: str, profile: str, cn: str, days: int) -> dict:
    serial = secrets.token_hex(16)
    ext = CA_EXT[profile].format(cn=cn)
    ca_run(cfg, f"""set -e; printf '{ext}' > /tmp/p.ext
        openssl x509 -req -in {csr_rel} -CA ca.crt -CAkey ca.key -set_serial 0x{serial} -days {days} -sha256 \\
          -extfile /tmp/p.ext -out {out_rel} 2>/dev/null; chmod 644 {out_rel}""")
    t = ca_run(cfg, f"openssl x509 -in {out_rel} -noout -enddate -fingerprint -sha256").stdout
    rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "serial": serial, "cn": cn, "profile": profile, "days": days,
           "not_after": re.search(r"notAfter=(.+)", t).group(1).strip(),
           "sha256": re.search(r"Fingerprint=([0-9A-F:]+)", t).group(1)}
    with open(PKI / "issued.jsonl", "a", encoding="utf-8") as f:         # nhật ký cấp phát (kiểm toán, thu hồi)
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def sign_file(cfg: Config, f: Path, quiet: bool = False) -> dict:
    """Ký một CSR theo CHÍNH SÁCH của CA: chỉ CN = <nút>.<domain> (máy chủ) hoặc fdw_reader (máy khách).
    CA tự đặt SAN/EKU/hạn — không chép phần mở rộng từ CSR."""
    if not (PKI / "ca.key").exists():
        die("chưa có CA — chạy make tls-ca-init")
    allowed = {cfg.fqdn(n): "server" for n in cfg.nodes()} | {ROLE: "client"}
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
    days = int(cfg.tls.get("cert_days", 90))
    rec = issue(cfg, rel, f"exchange/{f.stem}.crt", allowed[cn], cn, days)
    shutil.copy(PKI / "ca.crt", EXCHANGE / "ca.crt")
    if not quiet:
        print(f"  ký {f.name:<18} sha256 CSR {fp}…  CN={cn} ({allowed[cn]}) · {days} ngày · tới {rec['not_after']}")
    return rec


def sign(cfg: Config, files: list[str]):
    csrs = [Path(f) for f in files] or sorted(EXCHANGE.glob("*.csr"))
    if not csrs:
        die(f"không có tệp .csr nào trong {EXCHANGE.relative_to(ROOT)}")
    for f in csrs:
        sign_file(cfg, f)
    print("Gửi <tên>.crt + ca.crt về máy chứa nút (build/e3/exchange/) rồi chạy make tls-site-install ở đó.")


# ------------------------------------------------------------------ secure: cấp chứng chỉ cho toàn hệ
def wait_nodes(cfg: Config, timeout: int = 600):
    pending, shown, t0 = list(cfg.nodes()), set(), time.time()
    while pending:
        for n in list(pending):
            try:
                with cfg.connect(n, timeout=2, tls="prefer") as c:
                    c.execute("SELECT 1")
                pending.remove(n)
            except Exception:  # noqa: BLE001
                if n not in shown and cfg.machine_of(n) != cfg.here:
                    print(f"  đang chờ {cfg.label(n)} — hãy chạy `make all MACHINE={cfg.machine_of(n)}` trên máy đó")
                    shown.add(n)
        if pending:
            if time.time() - t0 > timeout:
                die(f"không kết nối được: {', '.join(pending)}")
            time.sleep(2)


def client_ok(cfg: Config) -> bool:
    d = tls_site.edir(cfg, cfg.central)
    out = tls_site.dx(cfg, cfg.central, f"""cd {d} 2>/dev/null && [ -f {ROLE}.crt ] && [ -f {ROLE}.key ] &&
        openssl verify -CAfile ca.crt {ROLE}.crt >/dev/null && openssl x509 -in {ROLE}.crt -noout
        -checkend {tls_site.RENEW_DAYS * 86400} >/dev/null && cat ca.crt | sha256sum""".replace("\n", " "), check=False)
    return hashlib.sha256((PKI / "ca.crt").read_bytes()).hexdigest() in out


def secure(cfg: Config):
    force = "--force" in sys.argv
    t0 = time.time()
    print("E3 · CA nội bộ")
    ca_init(cfg)
    TLS_OFF_MARK.unlink(missing_ok=True)
    print("E3 · chờ mọi nút")
    wait_nodes(cfg)
    print(f"E3 · chứng chỉ máy chủ cho {len(cfg.nodes())} nút (khoá sinh trong container của từng nút)")
    for n in cfg.nodes():
        st = tls_site.cert_state(cfg, n)
        if st["ok"] and st["same_ca"] and not force:
            print(f"  {n:<9} đã có chứng chỉ hợp lệ tới {st['not_after']} — giữ nguyên")
            continue
        tls_site.csr(cfg, n, quiet=True)
        rec = sign_file(cfg, EXCHANGE / f"{n}.csr", quiet=True)
        via = "docker exec" if tls_site.local(cfg, n) else "kênh quản trị SQL"
        print(f"  {n:<9} CN={cfg.fqdn(n)} · ký serial {rec['serial'][:12]}… tới {rec['not_after']} · cài qua {via}")
        tls_site.install(cfg, n, quiet=True)
    print(f"E3 · chứng chỉ máy khách {ROLE} cho trạm trung tâm {cfg.central}")
    if client_ok(cfg) and not force:
        print(f"  {cfg.central:<9} đã có chứng chỉ máy khách hợp lệ — giữ nguyên")
    else:
        tls_site.csr(cfg, cfg.central, client=True, quiet=True)
        sign_file(cfg, EXCHANGE / f"{ROLE}.csr", quiet=True)
        tls_site.install(cfg, cfg.central, client=True, quiet=True)
    print(f"E3 BẬT cho toàn hệ ({time.time() - t0:.1f}s). Mọi kết nối qua mạng: TLS ≥ 1.3, verify-full. "
          "Bước tiếp: make link (postgres_fdw qua TLS)")


# ------------------------------------------------------------------ DNS nội bộ (giả lập) ở trạm trung tâm
def resolve_in_central(cfg: Config, host: str) -> str:
    r = subprocess.run(["docker", "exec", cfg.container(cfg.central), "sh", "-c",
                        f"getent ahostsv4 {host} | awk 'NR==1{{print $1}}'"], capture_output=True, text=True)
    ip = r.stdout.strip()
    if not ip:
        die(f"không phân giải được {host} từ trạm trung tâm")
    return ip


def set_hosts(cfg: Config, on: bool = True, override: dict | None = None) -> list[str]:
    """/etc/hosts của container trung tâm: <nút>.<domain> -> IP mà trạm trung tâm dùng để tới nút.
    Bản thật: một vùng DNS riêng (Route 53 private zone, CoreDNS, MagicDNS). override: {nút: nút_đích} (failover E1)."""
    override = override or {}
    lines = []
    if on:
        for n in cfg.remote_sites() + ["ref"]:
            target = override.get(n, n)
            lines.append(f"{resolve_in_central(cfg, cfg.docker_addr(target)[0])} {cfg.fqdn(n)}")
    script = (f"grep -v '{cfg.domain}' /etc/hosts > /tmp/hosts.e3; "
              + "".join(f"echo '{l}' >> /tmp/hosts.e3; " for l in lines)
              + "cat /tmp/hosts.e3 > /etc/hosts; rm /tmp/hosts.e3")
    subprocess.run(["docker", "exec", "-u", "root", cfg.container(cfg.central), "sh", "-c", script], check=True)
    return lines


# ------------------------------------------------------------------ trạng thái, thử, tắt
def status(cfg: Config):
    print(f"TLS toàn hệ: {'BẬT' if cfg.tls_on else 'TẮT'}")
    for n in cfg.nodes():
        tls_site.status(cfg, [n])
    with cfg.connect(cfg.central) as c:
        rows = c.execute("SELECT s.srvname, s.srvoptions, u.umoptions FROM pg_foreign_server s "
                         "JOIN pg_user_mappings u ON u.srvid = s.oid ORDER BY 1").fetchall()
        for srv, so, uo in rows:
            so = dict(o.split("=", 1) for o in so or [])
            uo = dict(o.split("=", 1) for o in uo or [])
            print(f"  {srv:<12} host={so.get('host')} sslmode={so.get('sslmode', '-')} "
                  f"sslnegotiation={so.get('sslnegotiation', '-')} user={uo.get('user')} "
                  f"mật khẩu={'có' if 'password' in uo else 'không'} chứng chỉ={'có' if 'sslcert' in uo else 'không'}")
        for s in cfg.remote_sites():
            c.execute(f"SELECT count(*) FROM s_{s}.room_type")
        for s in cfg.remote_sites():
            with cfg.connect(s) as r:
                for u, ssl, ver, ciph, dn in r.execute(
                        "SELECT a.usename, s.ssl, s.version, s.cipher, s.client_dn FROM pg_stat_ssl s "
                        "JOIN pg_stat_activity a USING (pid) WHERE a.application_name = 'postgres_fdw'").fetchall():
                    print(f"  phiên fdw tại {s:<9}: user={u} ssl={ssl} {ver or ''} {ciph or ''} client_dn={dn or '-'}")


def test_client(cfg: Config) -> tuple[str, str]:
    """Chứng chỉ máy khách NGẮN HẠN (1 ngày) cho người vận hành chạy phép thử từ máy A."""
    ca_run(cfg, f"""set -e; umask 077
        openssl genpkey -algorithm EC -pkeyopt ec_paramgen_curve:P-256 -out test_client.key
        openssl req -new -key test_client.key -subj '/CN={ROLE}' -out test_client.csr""")
    issue(cfg, "test_client.csr", "test_client.crt", "client", ROLE, 1)
    (PKI / "test_client.csr").unlink()
    (PKI / "test_client.key").chmod(0o600)
    return str(PKI / "test_client.crt"), str(PKI / "test_client.key")


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
    """Thử từ máy A tới một trạm ở máy B (đi qua mạng thật)."""
    import psycopg
    if not cfg.tls_on:
        die("TLS đang tắt — chạy make secure")
    s = next((x for x in cfg.remote_sites() if cfg.machine_of(x) != cfg.machine_of(cfg.central)), cfg.remote_sites()[0])
    ip, port = cfg.host_addr(s)
    name = cfg.fqdn(s)
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
        ("T8 quản trị viên postgres + đúng mật khẩu nhưng KHÔNG mã hoá", False,
         dict(user=cfg.user, password=cfg.password, sslmode="disable")),
    ]
    print(f"Thử tới {cfg.label(s)}:")
    passed = 0
    for title, expect_ok, kw in cases:
        r = try_conn(cfg, s, **kw)
        ok = r.startswith("OK") == expect_ok
        passed += ok
        print(f"  [{'ĐẠT' if ok else 'SAI'}] {title}: {r}")
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
    if passed != total:
        sys.exit(1)


def off(cfg: Config):
    """Gỡ lỗi: tắt TLS ở mọi nút + postgres_fdw không mã hoá. `make secure` (hoặc make all) bật lại."""
    for n in cfg.nodes():
        tls_site.uninstall(cfg, n)
    PKI.mkdir(parents=True, exist_ok=True)
    TLS_OFF_MARK.write_text("make tls-off\n")
    set_hosts(cfg, on=False)
    import link
    link.main()
    print("TLS TẮT toàn hệ (tạm thời). Bật lại: make secure && make link")


def main():
    cfg = Config()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "sign":
        return sign(cfg, [a for a in sys.argv[2:] if not a.startswith("--")])
    {"secure": secure, "status": status, "test": test, "ca-init": ca_init, "off": off}.get(
        cmd, lambda _: die(__doc__))(cfg)


if __name__ == "__main__":
    main()
