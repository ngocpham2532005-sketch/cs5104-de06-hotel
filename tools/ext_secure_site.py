#!/usr/bin/env python3
"""E3 — chế độ PRD: cài TLS cho các trạm CỦA MÁY NÀY, chạy NGAY TẠI máy đó (chỉ thư viện chuẩn + docker CLI).

Khác chế độ lab (`make ext-secure`, máy A làm hết qua SQL):
  - khoá riêng của trạm được sinh TRONG container của trạm và không bao giờ rời khỏi đó;
  - máy chứa trạm chỉ gửi đi CSR (công khai) và nhận về chứng chỉ (công khai) — không cần ai có superuser qua mạng;
  - cài đặt bằng `docker exec` tại chỗ: kiểm tra chuỗi CA, khớp khoá, SAN, EKU, hạn dùng; sao lưu cấu hình;
    kiểm tra lại sau khi reload (TLS thật sự phục vụ đúng chứng chỉ mới); lỗi ở bất kỳ bước nào => hoàn tác.

Luồng (xem docs/NANG_CAO.md, E3 — chế độ PRD):
  máy chứa trạm  : python tools/ext_secure_site.py csr               -> build/e3/exchange/<trạm>.csr
  máy A (CA)     : python tools/ext_secure.py sign <trạm>.csr        -> <trạm>.crt + ca.crt
  máy chứa trạm  : python tools/ext_secure_site.py install           (đọc build/e3/exchange/<trạm>.crt, ca.crt)
  máy A          : python tools/ext_secure_site.py csr --client ; sign ; install --client ; make ext-secure-link

Lệnh:
  csr       [trạm…] [--client] [--rotate]   sinh khoá (nếu chưa có khoá chờ) + CSR
  install   [trạm…] [--client]              cài chứng chỉ đã ký, bật TLS, role fdw_reader, pg_hba
  status    [trạm…]                         cấu hình TLS, chứng chỉ đang dùng, số ngày còn hạn
  uninstall [trạm…]                         tắt TLS, xoá role + dòng pg_hba của E3 (giữ bản sao lưu)
  --version                                 mã băm của script (để so giữa các máy sau khi đồng bộ)
Không ghi trạm => mọi trạm xa nằm trên máy này (MACHINE=A|B, theo deploy.toml). Gia hạn = csr --rotate → sign → install.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from common import RESULTS, ROOT, Config, die

EXCHANGE = ROOT / "build" / "e3" / "exchange"
LOG_DIR = RESULTS / "ext"            # nhật ký riêng mỗi máy: e3_site_<máy>.log
ROLE = "fdw_reader"
HBA_BEGIN, HBA_END = "# >>> E3 ext-secure", "# <<< E3 ext-secure"
SUBDIR = "e3"
RENEW_WARN_DAYS = 30


class Fail(Exception):
    pass


# ------------------------------------------------------------------ tiện ích
def dx(cfg: Config, node: str, script: str, data: bytes | None = None, user: str = "postgres",
       check: bool = True) -> str:
    """Chạy sh trong container của trạm (tại máy này). `data` đưa vào stdin (dùng để ghi tệp, không qua dòng lệnh)."""
    r = subprocess.run(["docker", "exec", "-i", "-u", user, cfg.container(node), "sh", "-c", script],
                       input=data, capture_output=True)
    out, err = r.stdout.decode("utf-8", "replace"), r.stderr.decode("utf-8", "replace")
    if check and r.returncode != 0:
        raise Fail(err.strip() or out.strip() or f"lệnh lỗi (mã {r.returncode})")
    return out


def sql(cfg: Config, node: str, q: str) -> str:
    """psql qua unix socket TRONG container — không cần mật khẩu, không đi qua mạng."""
    return dx(cfg, node, f"psql -X -v ON_ERROR_STOP=1 -At -U {cfg.user} -d {cfg.db}", data=q.encode()).strip()


def edir(cfg: Config, node: str) -> str:
    return sql(cfg, node, "SHOW data_directory") + "/" + SUBDIR


def fqdn(cfg: Config, site: str) -> str:
    return f"{site}.{cfg.secure.get('domain', 'db.nhom8.internal')}"


def log(cfg: Config, action: str, node: str, **kw):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    rec = {"ts": dt.datetime.now().isoformat(timespec="seconds"), "machine": cfg.here, "action": action,
           "node": node, **kw}
    with open(LOG_DIR / f"e3_site_{cfg.here}.log", "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def running(cfg: Config, node: str) -> bool:
    r = subprocess.run(["docker", "inspect", "-f", "{{.State.Running}}", cfg.container(node)],
                       capture_output=True, text=True)
    return r.stdout.strip() == "true"


def targets(cfg: Config, names: list[str], client: bool) -> list[str]:
    if client:
        if cfg.machine_of(cfg.central) != cfg.here:
            die(f"--client phải chạy ở máy của trạm trung tâm ({cfg.machine_of(cfg.central)})")
        return [cfg.central]
    mine = [s for s in cfg.remote_sites() if cfg.machine_of(s) == cfg.here]
    for n in names:
        if n not in cfg.remote_sites():
            die(f"{n}: không phải trạm xa (các trạm xa: {', '.join(cfg.remote_sites())})")
        if n not in mine:
            die(f"{n} nằm ở máy {cfg.machine_of(n)}, không phải máy này ({cfg.here}) — chạy lệnh ở máy đó")
    sel = names or mine
    if not sel:
        die(f"máy {cfg.here} không có trạm xa nào")
    for n in sel:
        if not running(cfg, n):
            die(f"container {cfg.container(n)} không chạy trên máy này")
    return sel


def subject(cfg: Config, node: str, client: bool) -> tuple[str, str]:
    """(tên tệp trao đổi, CN)"""
    return (ROLE, ROLE) if client else (node, fqdn(cfg, node))


# ------------------------------------------------------------------ csr
def csr(cfg: Config, nodes: list[str], client: bool, rotate: bool):
    EXCHANGE.mkdir(parents=True, exist_ok=True)
    for n in nodes:
        name, cn = subject(cfg, n, client)
        d = edir(cfg, n)
        san = "" if client else f" -addext 'subjectAltName=DNS:{cn}'"
        out = dx(cfg, n, f"""set -e; umask 077; mkdir -p {d}/pending; cd {d}/pending
            {'rm -f ' + name + '.key; ' if rotate else ''}
            if [ ! -f {name}.key ]; then
              openssl genpkey -algorithm EC -pkeyopt ec_paramgen_curve:P-256 -out {name}.key 2>/dev/null; echo NEWKEY
            fi
            openssl req -new -key {name}.key -subj '/O=Nhom 8 CS5104/CN={cn}'{san} -out {name}.csr
            cat {name}.csr""")
        new_key = out.startswith("NEWKEY")
        pem = out[out.index("-----BEGIN"):]
        p = EXCHANGE / f"{name}.csr"
        p.write_text(pem, encoding="ascii")
        fp = hashlib.sha256(pem.encode()).hexdigest()[:16]
        log(cfg, "csr", n, cn=cn, new_key=new_key, csr_sha256=fp)
        print(f"  {n:<9} CN={cn}  khoá {'MỚI' if new_key else 'đang chờ (dùng lại)'} — nằm trong container, không xuất ra")
        print(f"            -> {p.relative_to(ROOT)}   sha256 {fp}…  (đối chiếu với máy A khi ký)")
    print("Bước tiếp: chép các tệp .csr sang máy A → `make ext-secure-sign` → chép <trạm>.crt + ca.crt về "
          "build/e3/exchange/ của máy này → `make ext-secure-site-install`.")


# ------------------------------------------------------------------ install
def check_cert(cfg: Config, n: str, d: str, name: str, cn: str, client: bool) -> dict:
    """Kiểm tra trong container trước khi dùng. Trả về thông tin chứng chỉ."""
    def run(script, why):
        try:
            return dx(cfg, n, f"cd {d}/pending && {script}")
        except Fail as e:
            raise Fail(f"{why}: {e}") from None
    run(f"openssl verify -CAfile ca.crt {name}.crt", "chứng chỉ không do CA nội bộ ký")
    a = run(f"openssl x509 -in {name}.crt -noout -pubkey | sha256sum", "đọc khoá công khai")
    b = run(f"openssl pkey -in {name}.key -pubout | sha256sum", "không có khoá chờ (chạy csr trước)")
    if a != b:
        raise Fail("chứng chỉ KHÔNG khớp khoá riêng đang chờ (ký nhầm CSR cũ?)")
    run(f"openssl x509 -in {name}.crt -noout -checkend 86400", "chứng chỉ hết hạn hoặc còn < 1 ngày")
    text = run(f"openssl x509 -in {name}.crt -noout -subject -enddate -fingerprint -sha256 -ext subjectAltName,extendedKeyUsage",
               "đọc chứng chỉ")
    if f"CN={cn}" not in text.replace(" = ", "="):
        raise Fail(f"CN không phải {cn}")
    if not client and f"DNS:{cn}" not in text:
        raise Fail(f"SAN không có DNS:{cn}")
    if ("TLS Web Client Authentication" if client else "TLS Web Server Authentication") not in text:
        raise Fail("extendedKeyUsage sai mục đích (server/client)")
    end = re.search(r"notAfter=(.+)", text).group(1).strip()
    fpr = re.search(r"Fingerprint=([0-9A-F:]+)", text).group(1)
    return {"not_after": end, "sha256": fpr}


def put(cfg: Config, n: str, path: str, data: bytes, mode: str):
    dx(cfg, n, f"umask 077; cat > {path}.tmp && chmod {mode} {path}.tmp && mv -f {path}.tmp {path}", data=data)


def install(cfg: Config, nodes: list[str], client: bool):
    for n in nodes:
        name, cn = subject(cfg, n, client)
        crt, ca = EXCHANGE / f"{name}.crt", EXCHANGE / "ca.crt"
        for f in (crt, ca):
            if not f.exists():
                die(f"thiếu {f.relative_to(ROOT)} — lấy từ máy A sau khi ký")
        d = edir(cfg, n)
        try:
            put(cfg, n, f"{d}/pending/{name}.crt", crt.read_bytes(), "644")
            put(cfg, n, f"{d}/pending/ca.crt", ca.read_bytes(), "644")
            info = check_cert(cfg, n, d, name, cn, client)
        except Fail as e:
            log(cfg, "install-rejected", n, error=str(e))
            die(f"{n}: TỪ CHỐI cài — {e}")
        print(f"  {n:<9} kiểm tra trước khi cài: chuỗi CA ✓  khớp khoá ✓  CN/SAN ✓  EKU ✓  hạn tới {info['not_after']}")
        (install_client if client else install_server)(cfg, n, d, name, info)


def install_client(cfg: Config, n: str, d: str, name: str, info: dict):
    dx(cfg, n, f"""set -e; cd {d}
        mkdir -p prev; for f in {name}.key {name}.crt ca.crt; do [ -f $f ] && cp -p $f prev/$f || true; done
        mv -f pending/{name}.key {name}.key; mv -f pending/{name}.crt {name}.crt; mv -f pending/ca.crt ca.crt
        rm -f pending/{name}.csr""")
    log(cfg, "install", n, kind="client", **info)
    print(f"  {n:<9} chứng chỉ máy khách {ROLE} đã cài ({d}); bước tiếp: make ext-secure-link")


HBA_BLOCK = (f"hostssl   {{db}}  {ROLE}  all  cert\n"
             f"hostnossl all    {ROLE}  all  reject\n"
             f"hostssl   all    {ROLE}  all  reject")


def set_hba(cfg: Config, n: str, block: str | None):
    hba = sql(cfg, n, "SHOW hba_file")
    text = dx(cfg, n, f"cat {hba}")
    if HBA_BEGIN in text:
        a, b = text.index(HBA_BEGIN), text.index(HBA_END) + len(HBA_END) + 1
        text = text[:a] + text[b:]
    if block:
        text = f"{HBA_BEGIN}\n{block}\n{HBA_END}\n" + text
    put(cfg, n, hba, text.encode(), "600")


def install_server(cfg: Config, n: str, d: str, name: str, info: dict):
    ts = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    hba = sql(cfg, n, "SHOW hba_file")
    dd = d.rsplit("/", 1)[0]
    # 1) sao lưu cấu hình + chứng chỉ đang dùng
    dx(cfg, n, f"""set -e; umask 077; mkdir -p {d}/backup/{ts}; cd {d}
        cp -p {hba} backup/{ts}/pg_hba.conf; cp -p {dd}/postgresql.auto.conf backup/{ts}/
        for f in server.key server.crt ca.crt; do [ -f $f ] && cp -p $f backup/{ts}/$f || true; done""")

    def rollback(why: str):
        dx(cfg, n, f"""cd {d}; cp -p backup/{ts}/pg_hba.conf {hba}; cp -p backup/{ts}/postgresql.auto.conf {dd}/
            for f in server.key server.crt ca.crt; do [ -f backup/{ts}/$f ] && cp -p backup/{ts}/$f $f || rm -f $f; done""",
           check=False)
        sql(cfg, n, "SELECT pg_reload_conf()")
        log(cfg, "install-rolled-back", n, error=why, backup=ts)
        die(f"{n}: LỖI sau khi cài — đã HOÀN TÁC về bản sao lưu {ts}: {why}")

    try:
        # 2) đưa khoá/chứng chỉ chờ vào dùng: chép sang tệp tạm rồi mv (nguyên tử); bản chờ GIỮ LẠI tới khi
        #    kiểm tra xong, nên nếu phải hoàn tác thì sửa lỗi xong cài lại được ngay, không cần CSR mới
        dx(cfg, n, f"""set -e; cd {d}
            for p in "{name}.key server.key" "{name}.crt server.crt" "ca.crt ca.crt"; do
              set -- $p; cp -p pending/$1 $2.tmp; mv -f $2.tmp $2; done""")
        # 3) cấu hình TLS, role chỉ đọc, pg_hba
        sql(cfg, n, "\n".join(f"ALTER SYSTEM SET {k} = '{v}';" for k, v in [
            ("ssl_cert_file", f"{d}/server.crt"), ("ssl_key_file", f"{d}/server.key"), ("ssl_ca_file", f"{d}/ca.crt"),
            ("ssl_min_protocol_version", "TLSv1.3"), ("ssl", "on")]))
        sql(cfg, n, f"""DO $$BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{ROLE}')
                          THEN CREATE ROLE {ROLE} LOGIN; END IF; END$$;
            GRANT CONNECT ON DATABASE {cfg.db} TO {ROLE}; GRANT USAGE ON SCHEMA public TO {ROLE};
            GRANT SELECT ON ALL TABLES IN SCHEMA public TO {ROLE};
            ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO {ROLE};""")
        set_hba(cfg, n, HBA_BLOCK.format(db=cfg.db))
        sql(cfg, n, "SELECT pg_reload_conf()")
        # 4) kiểm tra sau khi reload
        bad = sql(cfg, n, "SELECT count(*) FROM pg_hba_file_rules WHERE error IS NOT NULL")
        if bad != "0":
            raise Fail(f"pg_hba có {bad} dòng lỗi")
        tls = dx(cfg, n, f"psql -X -At 'host=localhost dbname={cfg.db} user={cfg.user} sslmode=require' "
                         "-c 'SELECT ssl, version FROM pg_stat_ssl WHERE pid = pg_backend_pid()'").strip()
        if not tls.startswith("t|TLSv1.3"):
            raise Fail(f"TLS chưa bật sau reload ({tls or 'không kết nối được'})")
        served = dx(cfg, n, "openssl s_client -connect localhost:5432 -alpn postgresql </dev/null 2>/dev/null "
                            "| openssl x509 -noout -fingerprint -sha256")
        if info["sha256"] not in served:
            raise Fail("máy chủ chưa phục vụ chứng chỉ mới (sai tệp hoặc khoá không đọc được)")
        if os.environ.get("E3_FAULT") == "after-reload":      # chỉ để kiểm thử đường hoàn tác
            raise Fail("lỗi giả lập (E3_FAULT=after-reload)")
    except Fail as e:
        rollback(str(e))
    dx(cfg, n, f"cd {d}/pending && rm -f {name}.key {name}.crt {name}.csr ca.crt")
    log(cfg, "install", n, kind="server", backup=ts, **info)
    print(f"  {n:<9} TLS 1.3 bật, đang phục vụ đúng chứng chỉ mới (sha256 {info['sha256'][:23]}…); "
          f"{ROLE} chỉ SELECT; pg_hba: chỉ TLS + cert. Sao lưu: {d}/backup/{ts}")


# ------------------------------------------------------------------ status / uninstall
def status(cfg: Config, nodes: list[str]):
    for n in nodes:
        d = edir(cfg, n)
        ssl = sql(cfg, n, "SELECT setting FROM pg_settings WHERE name = 'ssl'")
        role = sql(cfg, n, f"SELECT count(*) FROM pg_roles WHERE rolname = '{ROLE}'") == "1"
        hba = HBA_BEGIN in dx(cfg, n, f"cat {sql(cfg, n, 'SHOW hba_file')}")
        info = dx(cfg, n, f"cd {d} 2>/dev/null && [ -f server.crt ] && openssl x509 -in server.crt -noout -subject "
                          "-enddate -fingerprint -sha256", check=False)
        pend = dx(cfg, n, f"ls {d}/pending 2>/dev/null", check=False).split()
        line = f"  {n:<9} ssl={ssl} role {ROLE}={'có' if role else 'không'} pg_hba E3={'có' if hba else 'không'}"
        if info:
            end = re.search(r"notAfter=(.+)", info).group(1).strip()
            left = (dt.datetime.strptime(end, "%b %d %H:%M:%S %Y %Z") - dt.datetime.now(dt.UTC).replace(tzinfo=None)).days
            warn = "  ⚠ CẦN GIA HẠN (csr --rotate)" if left < RENEW_WARN_DAYS else ""
            line += f"\n            {re.search(r'subject=(.+)', info).group(1).strip()} · hết hạn {end} (còn {left} ngày){warn}"
        else:
            line += "\n            chưa có chứng chỉ máy chủ"
        if pend:
            line += f"\n            đang chờ: {' '.join(pend)}"
        print(line)


def uninstall(cfg: Config, nodes: list[str]):
    for n in nodes:
        d = edir(cfg, n)
        set_hba(cfg, n, None)
        sql(cfg, n, "\n".join(f"ALTER SYSTEM RESET {k};" for k in
                              ("ssl", "ssl_cert_file", "ssl_key_file", "ssl_ca_file", "ssl_min_protocol_version")))
        sql(cfg, n, "SELECT pg_reload_conf()")
        sql(cfg, n, f"""DO $$BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{ROLE}')
                          THEN EXECUTE 'DROP OWNED BY {ROLE}'; EXECUTE 'DROP ROLE {ROLE}'; END IF; END$$;""")
        dx(cfg, n, f"cd {d} 2>/dev/null && rm -rf server.key server.crt ca.crt pending prev || true")
        log(cfg, "uninstall", n)
        print(f"  {n:<9} TLS tắt, xoá role {ROLE} và dòng pg_hba của E3 (sao lưu giữ ở {d}/backup/)")


def version() -> str:
    h = hashlib.sha256()
    for f in ("tools/ext_secure_site.py", "tools/common.py"):
        h.update((ROOT / f).read_bytes().replace(b"\r\n", b"\n"))
    return h.hexdigest()[:12]


def main():
    args = sys.argv[1:]
    if "--version" in args:
        print(f"ext_secure_site {version()}")
        return
    if not args or args[0] not in ("csr", "install", "status", "uninstall"):
        die(__doc__)
    cmd, flags = args[0], {a for a in args[1:] if a.startswith("--")}
    names = [a for a in args[1:] if not a.startswith("--")]
    cfg = Config()
    client = "--client" in flags
    nodes = targets(cfg, names, client)
    print(f"E3 (PRD) · {cmd} · máy {cfg.here} · {', '.join(nodes)}{' (máy khách ' + ROLE + ')' if client else ''}")
    if cmd == "csr":
        csr(cfg, nodes, client, "--rotate" in flags)
    elif cmd == "install":
        install(cfg, nodes, client)
    elif cmd == "status":
        status(cfg, nodes)
    else:
        uninstall(cfg, nodes)


if __name__ == "__main__":
    main()
