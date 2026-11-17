#!/usr/bin/env python3
"""E3 — TLS cho MỘT nút (trạm hoặc CSDL đối chứng): khoá riêng sinh và nằm yên trong container của nút.

Hai cách chạy, cùng một mã:
  - tại máy chứa nút (chỉ thư viện chuẩn + docker):  python tools/tls_site.py csr|install|status|uninstall [nút…]
      => `docker exec` ngay trên máy đó; không ai cần quyền gì qua mạng (chế độ chặt, xem README);
  - từ máy A trong `make all` (tools/tls.py secure): nút ở máy khác được điều khiển qua KÊNH QUẢN TRỊ SQL
      (`COPY … FROM PROGRAM`, superuser) — lệnh openssl vẫn chạy TRONG container của nút, khoá vẫn không rời nút;
      qua mạng chỉ đi CSR và chứng chỉ (công khai).

Mỗi nút sau khi cài:
  ssl = on, TLS ≥ 1.3, chứng chỉ máy chủ <nút>.<domain> do CA nội bộ ký (SAN là TÊN, không có IP);
  pg_hba (đầu tệp, khớp trước): loopback trong container giữ nguyên; MỌI kết nối qua mạng không mã hoá bị từ chối
  (kể cả replication); fdw_reader (chỉ SELECT) chỉ vào được bằng chứng chỉ máy khách (`cert`).
Cài có kiểm tra (chuỗi CA, khớp khoá, CN/SAN, EKU, hạn), sao lưu, kiểm tra sau reload (đang phục vụ đúng
vân tay chứng chỉ mới) và TỰ HOÀN TÁC nếu lỗi.

  csr       [nút…] [--client] [--rotate]   sinh khoá (nếu chưa có khoá chờ) + CSR -> build/e3/exchange/<nút>.csr
  install   [nút…] [--client]              cài <nút>.crt + ca.crt từ build/e3/exchange/
  status    [nút…]                         TLS, chứng chỉ đang dùng, số ngày còn hạn
  uninstall [nút…]                         tắt TLS, bỏ dòng pg_hba của E3, xoá role fdw_reader (giữ bản sao lưu)
  --version                                mã băm script (so giữa các máy sau khi đồng bộ)
Không ghi nút => mọi nút trên máy này (MACHINE=A|B). --client: chứng chỉ máy khách fdw_reader của trạm trung tâm.
"""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys

from common import PKI, RESULTS, ROOT, Config, die

EXCHANGE = PKI / "exchange"
LOG_DIR = RESULTS / "ext"            # nhật ký riêng mỗi máy: e3_site_<máy>.log
ROLE = "fdw_reader"
HBA_BEGIN, HBA_END = "# >>> E3 tls", "# <<< E3 tls"
OLD_HBA_BEGIN, OLD_HBA_END = "# >>> E3 ext-secure", "# <<< E3 ext-secure"
SUBDIR = "e3"
RENEW_DAYS = 30


class Fail(Exception):
    pass


# ------------------------------------------------------------------ chạy lệnh trong container của nút
_conns: dict = {}


def local(cfg: Config, node: str) -> bool:
    return cfg.machine_of(node) == cfg.here


def dx(cfg: Config, node: str, script: str, data: bytes | None = None, user: str = "postgres",
       check: bool = True) -> str:
    """Chạy sh trong container của nút; `data` đưa vào stdin. Nút ở máy khác => kênh quản trị SQL."""
    if local(cfg, node):
        r = subprocess.run(["docker", "exec", "-i", "-u", user, cfg.container(node), "sh", "-c", script],
                           input=data, capture_output=True)
        rc, out, err = r.returncode, r.stdout, r.stderr
    else:
        if user != "postgres":
            die(f"{node}: lệnh quyền {user} chỉ chạy được tại máy chứa nút")
        rc, out, err = _remote(cfg, node, script, data or b"")
    out_s, err_s = out.decode("utf-8", "replace"), err.decode("utf-8", "replace")
    if check and rc != 0:
        raise Fail(err_s.strip() or out_s.strip() or f"lệnh lỗi (mã {rc})")
    return out_s


def _remote(cfg: Config, node: str, script: str, data: bytes) -> tuple[int, bytes, bytes]:
    """COPY … FROM PROGRAM: chạy trong container của nút (người dùng hệ điều hành postgres), lấy lại
    mã thoát + stdout + stderr dưới dạng base64 trên MỘT dòng (không đụng tới cú pháp văn bản của COPY)."""
    c = _conns.get(node)
    if c is None or c.closed:
        c = _conns[node] = cfg.connect(node, timeout=5, tls="prefer")
        c.execute("CREATE TEMP TABLE IF NOT EXISTS _e3(l text)")
    s64, d64 = base64.b64encode(script.encode()).decode(), base64.b64encode(data).decode()
    prog = (f"t=$(mktemp -d); echo {s64} | base64 -d > $t/s; echo {d64} | base64 -d > $t/i; "
            f"sh $t/s < $t/i > $t/o 2> $t/e; r=$?; "
            f"printf '%s|%s|%s' $r \"$(base64 -w0 < $t/o)\" \"$(base64 -w0 < $t/e)\"; rm -rf $t")
    c.execute("TRUNCATE _e3")
    c.execute(f"COPY _e3 FROM PROGRAM $cs5104${prog}$cs5104$")
    line = c.execute("SELECT l FROM _e3").fetchone()[0]
    rc, o, e = line.split("|")
    return int(rc), base64.b64decode(o), base64.b64decode(e)


def sql(cfg: Config, node: str, q: str) -> str:
    """psql qua unix socket TRONG container — không qua mạng, không cần mật khẩu."""
    return dx(cfg, node, f"psql -X -v ON_ERROR_STOP=1 -At -U {cfg.user} -d {cfg.db}", data=q.encode()).strip()


def edir(cfg: Config, node: str) -> str:
    return sql(cfg, node, "SHOW data_directory") + "/" + SUBDIR


def log(cfg: Config, action: str, node: str, **kw):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    rec = {"ts": dt.datetime.now().isoformat(timespec="seconds"), "machine": cfg.here,
           "via": "docker" if local(cfg, node) else "sql", "action": action, "node": node, **kw}
    with open(LOG_DIR / f"e3_site_{cfg.here}.log", "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def subject(cfg: Config, node: str, client: bool) -> tuple[str, str]:
    """(tên tệp trao đổi, CN)"""
    return (ROLE, ROLE) if client else (node, cfg.fqdn(node))


# ------------------------------------------------------------------ csr
def csr(cfg: Config, node: str, client: bool = False, rotate: bool = False, quiet: bool = False) -> str:
    EXCHANGE.mkdir(parents=True, exist_ok=True)
    name, cn = subject(cfg, node, client)
    d = edir(cfg, node)
    san = "" if client else f" -addext 'subjectAltName=DNS:{cn}'"
    out = dx(cfg, node, f"""set -e; umask 077; mkdir -p {d}/pending; cd {d}/pending
        {'rm -f ' + name + '.key' if rotate else ':'}
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
    log(cfg, "csr", node, cn=cn, new_key=new_key, csr_sha256=fp)
    if not quiet:
        print(f"  {node:<9} CN={cn}  khoá {'MỚI' if new_key else 'đang chờ (dùng lại)'} — nằm trong container, không xuất ra")
        print(f"            -> {p.relative_to(ROOT)}   sha256 {fp}…  (đối chiếu khi ký)")
    return fp


# ------------------------------------------------------------------ install
def check_cert(cfg: Config, n: str, d: str, name: str, cn: str, client: bool) -> dict:
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
    text = run(f"openssl x509 -in {name}.crt -noout -subject -enddate -fingerprint -sha256 "
               "-ext subjectAltName,extendedKeyUsage", "đọc chứng chỉ")
    if f"CN={cn}" not in text.replace(" = ", "="):
        raise Fail(f"CN không phải {cn}")
    if not client and f"DNS:{cn}" not in text:
        raise Fail(f"SAN không có DNS:{cn}")
    if ("TLS Web Client Authentication" if client else "TLS Web Server Authentication") not in text:
        raise Fail("extendedKeyUsage sai mục đích (server/client)")
    return {"not_after": re.search(r"notAfter=(.+)", text).group(1).strip(),
            "sha256": re.search(r"Fingerprint=([0-9A-F:]+)", text).group(1)}


def put(cfg: Config, n: str, path: str, data: bytes, mode: str):
    dx(cfg, n, f"umask 077; cat > {path}.tmp && chmod {mode} {path}.tmp && mv -f {path}.tmp {path}", data=data)


def install(cfg: Config, node: str, client: bool = False, quiet: bool = False):
    name, cn = subject(cfg, node, client)
    crt, ca = EXCHANGE / f"{name}.crt", EXCHANGE / "ca.crt"
    for f in (crt, ca):
        if not f.exists():
            die(f"thiếu {f.relative_to(ROOT)} — lấy từ máy A sau khi ký")
    d = edir(cfg, node)
    try:
        put(cfg, node, f"{d}/pending/{name}.crt", crt.read_bytes(), "644")
        put(cfg, node, f"{d}/pending/ca.crt", ca.read_bytes(), "644")
        info = check_cert(cfg, node, d, name, cn, client)
    except Fail as e:
        log(cfg, "install-rejected", node, error=str(e))
        die(f"{node}: TỪ CHỐI cài — {e}")
    if not quiet:
        print(f"  {node:<9} kiểm tra trước khi cài: chuỗi CA ✓  khớp khoá ✓  CN/SAN ✓  EKU ✓  hạn tới {info['not_after']}")
    (install_client if client else install_server)(cfg, node, d, name, info, quiet)


def install_client(cfg: Config, n: str, d: str, name: str, info: dict, quiet: bool):
    dx(cfg, n, f"""set -e; cd {d}
        mkdir -p prev; for f in {name}.key {name}.crt ca.crt; do [ -f $f ] && cp -p $f prev/$f || true; done
        for p in "{name}.key {name}.key" "{name}.crt {name}.crt" "ca.crt ca.crt"; do
          set -- $p; cp -p pending/$1 $2.tmp; mv -f $2.tmp $2; done
        rm -f pending/{name}.key pending/{name}.crt pending/{name}.csr pending/ca.crt""")
    log(cfg, "install", n, kind="client", **info)
    print(f"  {n:<9} chứng chỉ máy khách {ROLE}: đã cài ({d})" + ("" if quiet else "; bước tiếp: make link"))


def hba_block(cfg: Config) -> str:
    return "\n".join([
        "host      all          all         127.0.0.1/32  trust     # trong container: giữ như mặc định",
        "host      all          all         ::1/128       trust",
        "host      replication  all         127.0.0.1/32  trust",
        f"hostssl   {cfg.db:<12} {ROLE:<11} all           cert      # fdw: chỉ bằng chứng chỉ máy khách",
        f"hostssl   all          {ROLE:<11} all           reject",
        "hostnossl all          all         all           reject    # qua mạng mà không mã hoá: từ chối",
        "hostnossl replication  all         all           reject",
    ])


def set_hba(cfg: Config, n: str, block: str | None):
    hba = sql(cfg, n, "SHOW hba_file")
    text = dx(cfg, n, f"cat {hba}")
    for b, e in ((HBA_BEGIN, HBA_END), (OLD_HBA_BEGIN, OLD_HBA_END)):
        if b in text:
            i, j = text.index(b), text.index(e) + len(e) + 1
            text = text[:i] + text[j:]
    if block:
        text = f"{HBA_BEGIN}\n{block}\n{HBA_END}\n" + text
    put(cfg, n, hba, text.encode(), "600")


def install_server(cfg: Config, n: str, d: str, name: str, info: dict, quiet: bool):
    ts = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    hba = sql(cfg, n, "SHOW hba_file")
    dd = d.rsplit("/", 1)[0]
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
        # cp sang tệp tạm rồi mv (nguyên tử); bản chờ GIỮ LẠI tới khi kiểm tra xong để hoàn tác xong cài lại được
        dx(cfg, n, f"""set -e; cd {d}
            for p in "{name}.key server.key" "{name}.crt server.crt" "ca.crt ca.crt"; do
              set -- $p; cp -p pending/$1 $2.tmp; mv -f $2.tmp $2; done""")
        sql(cfg, n, "\n".join(f"ALTER SYSTEM SET {k} = '{v}';" for k, v in [
            ("ssl_cert_file", f"{d}/server.crt"), ("ssl_key_file", f"{d}/server.key"), ("ssl_ca_file", f"{d}/ca.crt"),
            ("ssl_min_protocol_version", "TLSv1.3"), ("ssl", "on")]))
        sql(cfg, n, f"""DO $$BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{ROLE}')
                          THEN CREATE ROLE {ROLE} LOGIN; END IF; END$$;
            GRANT CONNECT ON DATABASE {cfg.db} TO {ROLE}; GRANT USAGE ON SCHEMA public TO {ROLE};
            GRANT SELECT ON ALL TABLES IN SCHEMA public TO {ROLE};
            ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO {ROLE};""")
        set_hba(cfg, n, hba_block(cfg))
        sql(cfg, n, "SELECT pg_reload_conf()")
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
    print(f"  {n:<9} TLS 1.3 bật · phục vụ đúng chứng chỉ mới (sha256 {info['sha256'][:23]}…) · "
          f"qua mạng chỉ nhận TLS · {ROLE} chỉ SELECT, chỉ bằng chứng chỉ" + ("" if quiet else f" · sao lưu {ts}"))


# ------------------------------------------------------------------ trạng thái
def cert_state(cfg: Config, n: str) -> dict:
    """Nút đã có chứng chỉ hợp lệ của CA hiện tại, còn hạn > RENEW_DAYS, TLS bật và pg_hba đúng chưa."""
    d = edir(cfg, n)
    ca_local = (PKI / "ca.crt").read_bytes() if (PKI / "ca.crt").exists() else b""
    out = dx(cfg, n, f"""cd {d} 2>/dev/null || exit 0
        [ -f server.crt ] || exit 0
        openssl x509 -in server.crt -noout -subject -enddate -fingerprint -sha256
        openssl x509 -in server.crt -noout -checkend {RENEW_DAYS * 86400} >/dev/null && echo FRESH=1
        cat ca.crt | sha256sum""", check=False)
    ssl = sql(cfg, n, "SELECT setting FROM pg_settings WHERE name = 'ssl'")
    hba = HBA_BEGIN in dx(cfg, n, f"cat {sql(cfg, n, 'SHOW hba_file')}")
    st = {"ssl": ssl == "on", "hba": hba, "has_cert": "notAfter=" in out, "fresh": "FRESH=1" in out,
          "same_ca": hashlib.sha256(ca_local).hexdigest() in out if ca_local else False}
    if st["has_cert"]:
        st["not_after"] = re.search(r"notAfter=(.+)", out).group(1).strip()
        st["subject"] = re.search(r"subject=(.+)", out).group(1).strip()
    st["ok"] = all(st[k] for k in ("ssl", "hba", "has_cert", "fresh")) and (st["same_ca"] or not ca_local)
    return st


def status(cfg: Config, nodes: list[str]):
    for n in nodes:
        st = cert_state(cfg, n)
        line = f"  {n:<9} ssl={'on' if st['ssl'] else 'off'} · pg_hba E3={'có' if st['hba'] else 'không'}"
        if st["has_cert"]:
            end = dt.datetime.strptime(st["not_after"], "%b %d %H:%M:%S %Y %Z")
            left = (end - dt.datetime.now(dt.UTC).replace(tzinfo=None)).days
            warn = "  ⚠ CẦN GIA HẠN" if not st["fresh"] else ""
            line += f"\n            {st['subject']} · hết hạn {st['not_after']} (còn {left} ngày){warn}"
        else:
            line += " · chưa có chứng chỉ máy chủ"
        print(line)


def uninstall(cfg: Config, n: str):
    d = edir(cfg, n)
    set_hba(cfg, n, None)
    sql(cfg, n, "\n".join(f"ALTER SYSTEM RESET {k};" for k in
                          ("ssl", "ssl_cert_file", "ssl_key_file", "ssl_ca_file", "ssl_min_protocol_version")))
    sql(cfg, n, "SELECT pg_reload_conf()")
    sql(cfg, n, f"""DO $$BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{ROLE}')
                      THEN EXECUTE 'DROP OWNED BY {ROLE}'; EXECUTE 'DROP ROLE {ROLE}'; END IF; END$$;""")
    dx(cfg, n, f"cd {d} 2>/dev/null && rm -rf server.key server.crt ca.crt pending prev || true")
    log(cfg, "uninstall", n)
    print(f"  {n:<9} TLS tắt, bỏ dòng pg_hba của E3, xoá role {ROLE} (sao lưu giữ ở {d}/backup/)")


# ------------------------------------------------------------------ CLI tại từng máy
def running(cfg: Config, node: str) -> bool:
    r = subprocess.run(["docker", "inspect", "-f", "{{.State.Running}}", cfg.container(node)],
                       capture_output=True, text=True)
    return r.stdout.strip() == "true"


def targets(cfg: Config, names: list[str], client: bool) -> list[str]:
    if client:
        if not local(cfg, cfg.central):
            die(f"--client phải chạy ở máy của trạm trung tâm ({cfg.machine_of(cfg.central)})")
        return [cfg.central]
    mine = [n for n in cfg.nodes() if local(cfg, n)]
    for n in names:
        if n not in cfg.nodes():
            die(f"{n}: không có nút này (các nút: {', '.join(cfg.nodes())})")
        if n not in mine:
            die(f"{n} nằm ở máy {cfg.machine_of(n)}, không phải máy này ({cfg.here}) — chạy lệnh ở máy đó")
    sel = names or mine
    for n in sel:
        if not running(cfg, n):
            die(f"container {cfg.container(n)} không chạy trên máy này")
    return sel


def version() -> str:
    h = hashlib.sha256()
    for f in ("tools/tls_site.py", "tools/common.py"):
        h.update((ROOT / f).read_bytes().replace(b"\r\n", b"\n"))
    return h.hexdigest()[:12]


def main():
    args = sys.argv[1:]
    if "--version" in args:
        print(f"tls_site {version()}")
        return
    if not args or args[0] not in ("csr", "install", "status", "uninstall"):
        die(__doc__)
    cmd, flags = args[0], {a for a in args[1:] if a.startswith("--")}
    names = [a for a in args[1:] if not a.startswith("--")]
    cfg = Config()
    client = "--client" in flags
    nodes = targets(cfg, names, client)
    print(f"E3 · {cmd} · máy {cfg.here} · {', '.join(nodes)}{' (máy khách ' + ROLE + ')' if client else ''}")
    for n in nodes:
        if cmd == "csr":
            csr(cfg, n, client, "--rotate" in flags)
        elif cmd == "install":
            install(cfg, n, client)
        elif cmd == "uninstall":
            uninstall(cfg, n)
    if cmd == "csr":
        print("Bước tiếp: chép .csr sang máy A → `make tls-sign` → chép <nút>.crt + ca.crt về build/e3/exchange/ "
              "của máy này → `make tls-site-install`.")
    if cmd == "status":
        status(cfg, nodes)


if __name__ == "__main__":
    main()
