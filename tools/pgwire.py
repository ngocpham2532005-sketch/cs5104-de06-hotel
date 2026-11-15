"""
pgwire.py — client PostgreSQL tối giản, thuần Python (chỉ thư viện chuẩn).

Dùng cho nạp dữ liệu, check, bench, giao diện nhập liệu và dashboard để cả hệ
chỉ cần Python >= 3.11 + Docker, không phải `pip install` gì.

Hỗ trợ: xác thực trust / cleartext / md5 / SCRAM-SHA-256; simple query
(nhiều câu lệnh trong một chuỗi); COPY ... FROM STDIN. Giá trị trả về ở dạng
text, được đổi sang int/float/bool theo OID kiểu.
"""
import base64, hashlib, hmac, os, socket, struct
from decimal import Decimal


class PgError(Exception):
    def __init__(self, fields):
        self.fields = fields
        self.code = fields.get("C", "")
        super().__init__(f"{fields.get('S', 'ERROR')} {self.code}: {fields.get('M', '')}"
                         + (f" ({fields['D']})" if "D" in fields else ""))


INT_OIDS = {20, 21, 23, 26}
FLOAT_OIDS = {700, 701}


def _conv(oid, raw):
    if raw is None:
        return None
    s = raw.decode("utf-8")
    if oid in INT_OIDS:
        return int(s)
    if oid == 1700:
        return Decimal(s)
    if oid in FLOAT_OIDS:
        return float(s)
    if oid == 16:
        return s == "t"
    return s


def lit(v):
    """Đổi giá trị Python thành literal SQL an toàn (standard_conforming_strings=on)."""
    if v is None:
        return "NULL"
    if v is True:
        return "true"
    if v is False:
        return "false"
    if isinstance(v, (int, float, Decimal)):
        return str(v)
    s = str(v)
    if "\x00" in s:
        raise ValueError("NUL byte in string")
    return "'" + s.replace("'", "''") + "'"


class Result:
    def __init__(self):
        self.columns, self.rows, self.status = [], [], ""

    def __repr__(self):
        return f"<Result {self.status} {len(self.rows)} rows>"


class Connection:
    def __init__(self, host, port, user, password, dbname, connect_timeout=5, timeout=None,
                 application_name="cs5104"):
        self.sock = socket.create_connection((host, int(port)), timeout=connect_timeout)
        self.sock.settimeout(connect_timeout)
        self.buf = b""
        self.user, self.password = user, password
        params = {"user": user, "database": dbname, "client_encoding": "UTF8",
                  "application_name": application_name}
        body = struct.pack("!i", 196608) + b"".join(
            k.encode() + b"\0" + v.encode() + b"\0" for k, v in params.items()) + b"\0"
        self.sock.sendall(struct.pack("!i", len(body) + 4) + body)
        self._auth()
        self.sock.settimeout(timeout)

    # ---- I/O cơ bản
    def _recv(self, n):
        while len(self.buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionError("server closed the connection")
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def _msg(self):
        t = self._recv(1)
        ln = struct.unpack("!i", self._recv(4))[0]
        return t, self._recv(ln - 4)

    def _send(self, t, payload=b""):
        self.sock.sendall(t + struct.pack("!i", len(payload) + 4) + payload)

    @staticmethod
    def _err(payload):
        f = {}
        for part in payload.split(b"\0"):
            if part:
                f[chr(part[0])] = part[1:].decode("utf-8", "replace")
        return f

    # ---- xác thực
    def _auth(self):
        nonce = client_first_bare = salted = auth_msg = None
        while True:
            t, p = self._msg()
            if t == b"E":
                raise PgError(self._err(p))
            if t == b"R":
                code = struct.unpack("!i", p[:4])[0]
                if code == 0:
                    continue
                if code == 3:
                    self._send(b"p", self.password.encode() + b"\0")
                elif code == 5:
                    salt = p[4:8]
                    inner = hashlib.md5((self.password + self.user).encode()).hexdigest()
                    outer = "md5" + hashlib.md5(inner.encode() + salt).hexdigest()
                    self._send(b"p", outer.encode() + b"\0")
                elif code == 10:
                    nonce = base64.b64encode(os.urandom(18)).decode()
                    client_first_bare = f"n=,r={nonce}"
                    cf = ("n,," + client_first_bare).encode()
                    self._send(b"p", b"SCRAM-SHA-256\0" + struct.pack("!i", len(cf)) + cf)
                elif code == 11:
                    server_first = p[4:].decode()
                    kv = dict(x.split("=", 1) for x in server_first.split(","))
                    if not kv["r"].startswith(nonce):
                        raise ConnectionError("SCRAM nonce mismatch")
                    salted = hashlib.pbkdf2_hmac("sha256", self.password.encode(),
                                                 base64.b64decode(kv["s"]), int(kv["i"]))
                    final_wo_proof = f"c=biws,r={kv['r']}"
                    auth_msg = f"{client_first_bare},{server_first},{final_wo_proof}".encode()
                    ckey = hmac.new(salted, b"Client Key", hashlib.sha256).digest()
                    sig = hmac.new(hashlib.sha256(ckey).digest(), auth_msg, hashlib.sha256).digest()
                    proof = base64.b64encode(bytes(a ^ b for a, b in zip(ckey, sig))).decode()
                    self._send(b"p", f"{final_wo_proof},p={proof}".encode())
                elif code == 12:
                    skey = hmac.new(salted, b"Server Key", hashlib.sha256).digest()
                    expect = base64.b64encode(hmac.new(skey, auth_msg, hashlib.sha256).digest()).decode()
                    if dict(x.split("=", 1) for x in p[4:].decode().split(",")).get("v") != expect:
                        raise ConnectionError("SCRAM server signature mismatch")
                else:
                    raise ConnectionError(f"unsupported auth method {code}")
            elif t == b"Z":
                return

    # ---- truy vấn
    def execute(self, sql, copy_data=None):
        """Chạy một chuỗi SQL (có thể nhiều câu). Trả về danh sách Result, mỗi câu một Result.
        copy_data: bytes/iterable[bytes] cho COPY ... FROM STDIN."""
        self._send(b"Q", sql.encode("utf-8") + b"\0")
        results, cur, error = [], Result(), None
        oids = []
        while True:
            t, p = self._msg()
            if t == b"T":
                n = struct.unpack("!h", p[:2])[0]; pos = 2
                cur.columns, oids = [], []
                for _ in range(n):
                    end = p.index(b"\0", pos)
                    cur.columns.append(p[pos:end].decode()); pos = end + 1
                    oids.append(struct.unpack("!i", p[pos + 6:pos + 10])[0]); pos += 18
            elif t == b"D":
                n = struct.unpack("!h", p[:2])[0]; pos = 2; row = []
                for i in range(n):
                    ln = struct.unpack("!i", p[pos:pos + 4])[0]; pos += 4
                    if ln < 0:
                        row.append(None)
                    else:
                        row.append(_conv(oids[i], p[pos:pos + ln])); pos += ln
                cur.rows.append(tuple(row))
            elif t == b"C":
                cur.status = p[:-1].decode(); results.append(cur); cur = Result()
            elif t == b"I":
                results.append(cur); cur = Result()
            elif t == b"G":
                try:
                    if copy_data is None:
                        raise ValueError("COPY FROM STDIN needs copy_data")
                    chunks = [copy_data] if isinstance(copy_data, (bytes, bytearray)) else copy_data
                    for ch in chunks:
                        for i in range(0, len(ch), 1 << 16):
                            self._send(b"d", bytes(ch[i:i + (1 << 16)]))
                    self._send(b"c")
                except Exception as e:  # báo cho server huỷ COPY
                    self._send(b"f", str(e).encode() + b"\0")
            elif t == b"E":
                error = PgError(self._err(p))
            elif t == b"Z":
                if error:
                    raise error
                return results
            # N (notice), S (parameter status), A (notify): bỏ qua

    def query(self, sql):
        """Chạy một câu, trả về (columns, rows) của kết quả cuối cùng có dữ liệu."""
        res = self.execute(sql)
        for r in reversed(res):
            if r.columns:
                return r.columns, r.rows
        return [], []

    def scalar(self, sql):
        _, rows = self.query(sql)
        return rows[0][0] if rows else None

    def close(self):
        try:
            self._send(b"X")
            self.sock.close()
        except OSError:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()
