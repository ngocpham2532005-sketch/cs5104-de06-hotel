"""Tiện ích web dùng chung cho entry.py và dash.py (chỉ thư viện chuẩn)."""
import json, sys, traceback
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import cfg  # noqa: E402,F401


def _default(o):
    if isinstance(o, Decimal):
        return float(o)
    return str(o)


class Handler(BaseHTTPRequestHandler):
    routes_get, routes_post, page = {}, {}, ""

    def log_message(self, fmt, *args):  # gọn log
        pass

    def _send(self, code, body, ctype):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False, default=_default), "application/json; charset=utf-8")

    def _dispatch(self, routes, arg):
        u = urlparse(self.path)
        if u.path == "/" and self.command == "GET":
            return self._send(200, self.page, "text/html; charset=utf-8")
        fn = routes.get(u.path)
        if not fn:
            return self.json({"error": "not found"}, 404)
        try:
            self.json(fn(arg if arg is not None else {k: v[0] for k, v in parse_qs(u.query).items()}))
        except UserError as e:
            self.json({"ok": False, "error": str(e)}, 400)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            self.json({"ok": False, "error": f"{type(e).__name__}: {e}"}, 500)

    def do_GET(self):
        self._dispatch(self.routes_get, None)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        self._dispatch(self.routes_post, body)


class UserError(Exception):
    pass


def serve(port, page, get, post=None, title=""):
    H = type("H", (Handler,), {"routes_get": get, "routes_post": post or {}, "page": page})
    srv = ThreadingHTTPServer(("0.0.0.0", port), H)
    print(f"{title} chạy tại http://localhost:{port}  (Ctrl+C để dừng)", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


CSS = """
*{box-sizing:border-box} body{font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;margin:0;background:#f5f6f8;color:#1d2330}
header{background:#1d2330;color:#fff;padding:14px 24px;display:flex;align-items:baseline;gap:16px}
header h1{font-size:18px;margin:0;font-weight:600} header span{opacity:.7;font-size:13px}
main{padding:20px 24px;max-width:1280px;margin:auto}
.card{background:#fff;border:1px solid #e1e4ea;border-radius:10px;padding:16px;margin-bottom:16px}
h2{font-size:15px;margin:0 0 12px} label{display:block;font-size:12px;color:#5a6275;margin:8px 0 3px}
input,select{width:100%;padding:7px 9px;border:1px solid #cfd4dd;border-radius:6px;font:inherit;background:#fff}
button{background:#2457d6;color:#fff;border:0;border-radius:6px;padding:8px 14px;font:inherit;cursor:pointer;margin-top:12px}
button.secondary{background:#e8ecf5;color:#1d2330} button:disabled{opacity:.5}
.grid{display:grid;gap:16px} .g2{grid-template-columns:1fr 1fr} .g3{grid-template-columns:repeat(3,1fr)} .g4{grid-template-columns:repeat(4,1fr)}
table{border-collapse:collapse;width:100%;font-size:13px} th,td{text-align:left;padding:4px 6px;border-bottom:1px solid #eef0f4}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}
.ok{color:#137333}.bad{color:#c5221f}.muted{color:#7a8195;font-size:12px}
.msg{white-space:pre-wrap;font-size:13px;padding:10px;border-radius:6px;margin-top:12px}
.msg.ok{background:#e6f4ea}.msg.bad{background:#fce8e6}
.chk{display:flex;align-items:center;gap:6px;margin-top:8px;font-size:13px}.chk input{width:auto}
"""
