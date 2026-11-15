"""Đọc deploy.toml; dùng chung cho mọi công cụ. Biến môi trường DEPLOY=đường_dẫn để dùng tệp khác."""
import os, sys, tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import pgwire  # noqa: E402

CFG_PATH = Path(os.environ.get("DEPLOY", ROOT / "deploy.toml"))
CFG = tomllib.loads(CFG_PATH.read_text(encoding="utf-8"))
DB = CFG["db"]
SIZE = os.environ.get("SIZE", DB.get("size", "lab"))
SITES = ["dalat", "nhatrang", "phuquoc", "danang"]          # thứ tự cố định theo đề
CENTRAL = next(s for s, v in CFG["sites"].items() if v.get("central"))
REMOTE = [s for s in SITES if s != CENTRAL]
REGION_VN = {"dalat": "Đà Lạt", "nhatrang": "Nha Trang", "phuquoc": "Phú Quốc", "danang": "Đà Nẵng"}

# Bảng bị chia (theo vùng khách sạn) và bảng sao chép ra mọi trạm. Thứ tự = cha trước, con sau.
REPLICATED = ["room_type", "tour_group"]
FRAGMENTED = ["hotel", "room", "booking", "req_tour", "req_business", "req_family", "req_family_child"]
ALL_TABLES = REPLICATED + FRAGMENTED
PK = {"room_type": ["room_type_code"], "tour_group": ["tour_group_id"], "hotel": ["hotel_id"],
      "room": ["room_id"], "booking": ["booking_id"], "req_tour": ["booking_id"],
      "req_business": ["booking_id"], "req_family": ["booking_id"],
      "req_family_child": ["booking_id", "seq"]}

DATA_DIR = ROOT / "datagen" / "de06_hotel" / "output" / SIZE
SITE_DIR = DATA_DIR / "sites"
RESULTS = ROOT / "results"


def site(s):
    v = CFG["sites"][s]
    m = v["machine"]
    return {"name": s, "machine": m, "ip": CFG["machines"][m]["ip"], "port": v["port"],
            "site_no": v["site_no"], "central": bool(v.get("central"))}


def connect(s, db=None, timeout=None, connect_timeout=5, app="cs5104"):
    info = site(s)
    return pgwire.Connection(info["ip"], info["port"], DB["user"], DB["password"],
                             db or DB["dbname"], connect_timeout=connect_timeout,
                             timeout=timeout, application_name=app)


def connect_ref(**kw):
    return connect(CENTRAL, db=DB["refdb"], **kw)


def sites_on(machine):
    return [s for s in SITES if site(s)["machine"] == machine]
