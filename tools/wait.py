"""Chờ đến khi mọi trạm nhận kết nối (máy B phải đã `make up MACHINE=B`)."""
import sys, time
from cfg import SITES, connect, site
from pgwire import PgError

timeout = float(sys.argv[1]) if len(sys.argv) > 1 else 600
t0, last = time.time(), None
while True:
    down = []
    for s in SITES:
        try:
            connect(s, db="postgres", connect_timeout=2).close()
        except PgError as e:   # trạm chạy nhưng từ chối đăng nhập => không chờ nữa
            if e.code == "28P01":
                sys.exit(f"Trạm {s} từ chối mật khẩu trong deploy.toml. Nếu trước đó đã chạy với mật khẩu khác, "
                         f"xoá volume cũ (onebox down / make down) rồi chạy lại.")
            down.append(f"{s} ({e})")
        except Exception:  # noqa: BLE001
            down.append(f"{s} (máy {site(s)['machine']} {site(s)['ip']}:{site(s)['port']})")
    if not down:
        print("Đủ 4 trạm đã sẵn sàng."); break
    if time.time() - t0 > timeout:
        sys.exit("Hết thời gian chờ, chưa kết nối được: " + ", ".join(down))
    msg = "Đang chờ: " + ", ".join(down)
    if msg != last:
        print(msg + "  — ở máy B chạy `make up MACHINE=B`", flush=True); last = msg
    time.sleep(2)
