"""Phần dùng chung cho giao diện nhập liệu và dashboard."""
import json
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
from common import ALL_TABLES, RESULTS, SITES_ORDER, Config  # noqa: E402

cfg = Config()
REGION_NAME = {"dalat": "Đà Lạt", "nhatrang": "Nha Trang", "phuquoc": "Phú Quốc", "danang": "Đà Nẵng"}
WEIGHTS = {"dalat": 0.20, "nhatrang": 0.26, "phuquoc": 0.24, "danang": 0.30}
EVENTS = RESULTS / "events.jsonl"


def site_label(site: str) -> str:
    m = cfg.machine_of(site)
    return f"trạm **{site}** ({REGION_NAME.get(site, site)}) · máy **{m}** · {cfg.machine_ip(site)}:{cfg.node(site)['port']}"


def connect(site: str, timeout: int = 2, autocommit: bool = True):
    """Mọi kết nối của giao diện/dashboard đi qua TLS verify-full (E3) khi hệ bật TLS."""
    return cfg.connect(site, timeout=timeout, autocommit=autocommit, app="cs5104_app")


def log_event(kind: str, site: str, msg: str):
    RESULTS.mkdir(exist_ok=True)
    rec = {"t": datetime.now().strftime("%H:%M:%S"), "ts": time.time(), "kind": kind, "site": site, "msg": msg}
    with open(EVENTS, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def read_events(n: int = 40):
    if not EVENTS.exists():
        return []
    lines = EVENTS.read_text(encoding="utf-8").splitlines()[-n:]
    return [json.loads(x) for x in reversed(lines)]


def group_code(tg: int) -> str:
    return f"TG{tg:04d}"


def build_request(guest_type: str, f: dict, tour_group_id: int | None):
    """jsonb + các dòng bản quan hệ tương đương — sinh từ CÙNG một dict để luôn nhất quán."""
    if guest_type == "tour":
        req = {"group_code": group_code(tour_group_id), "meal_plan": f["meal_plan"], "guide_room": bool(f["guide_room"])}
        rel = [("req_tour", ["group_code", "meal_plan", "guide_room"], [req["group_code"], req["meal_plan"], req["guide_room"]])]
    elif guest_type == "business":
        req = {"company": f["company"], "tax_code": f["tax_code"], "late_checkout": bool(f["late_checkout"])}
        rel = [("req_business", ["company", "tax_code", "late_checkout"], [req["company"], req["tax_code"], req["late_checkout"]])]
    else:
        ages = [int(a) for a in f["children_ages"]]
        req = {"extra_bed": bool(f["extra_bed"]), "children_ages": ages, "airport_pickup": bool(f["airport_pickup"])}
        rel = [("req_family", ["extra_bed", "airport_pickup"], [req["extra_bed"], req["airport_pickup"]])]
        rel += [("req_family_child", ["seq", "age"], [i + 1, a]) for i, a in enumerate(ages)]
    return req, rel


def write_booking(conn, b: dict, booking_id: int | None = None) -> int:
    """Ghi booking (jsonb) + bản quan hệ trong MỘT giao dịch. booking_id=None -> lấy từ sequence của trạm."""
    from psycopg.types.json import Jsonb
    req, rel = build_request(b["guest_type"], b["fields"], b.get("tour_group_id"))
    with conn.transaction():
        cols = ["room_id", "guest_name", "check_in", "nights", "guest_type", "tour_group_id", "request"]
        vals = [b["room_id"], b["guest_name"], b["check_in"], b["nights"], b["guest_type"], b.get("tour_group_id"), Jsonb(req)]
        if booking_id is not None:
            cols, vals = ["booking_id"] + cols, [booking_id] + vals
        bid = conn.execute(f"INSERT INTO booking ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))}) "
                           "RETURNING booking_id", vals).fetchone()[0]
        for table, c, v in rel:
            conn.execute(f"INSERT INTO {table} (booking_id, {', '.join(c)}) VALUES (%s, {', '.join(['%s'] * len(c))})",
                         [bid] + v)
    return bid
