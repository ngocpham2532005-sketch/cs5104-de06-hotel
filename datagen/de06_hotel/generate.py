#!/usr/bin/env python3
"""
CS5104 — Hệ cơ sở dữ liệu nâng cao · Project nhóm cuối kỳ
Bộ sinh dữ liệu Đề 6: Chuỗi khách sạn nghỉ dưỡng

Cách chạy (Python >= 3.11, chỉ dùng thư viện chuẩn):
    python3 generate.py --size mini     # bộ nhỏ để kiểm tra bằng mắt
    python3 generate.py --size lab      # bộ dùng để đo
Kết quả: output/<size>/<bảng>.csv (mỗi bảng của lược đồ tập trung một tệp) và output/<size>/summary.json.

Seed và tham số đã cố định theo đề — KHÔNG SỬA tệp này. Cùng seed => cùng dữ liệu trên mọi máy.
Cột jsonb được ghi trong CSV dưới dạng chuỗi JSON; nạp bằng COPY ... WITH (FORMAT csv, HEADER true).
"""
# ======================================================================
# Phần dùng chung — KHÔNG SỬA
# ======================================================================
import argparse, csv, json, random, bisect, datetime as dt
from pathlib import Path

HO = ["Nguyễn","Trần","Lê","Phạm","Hoàng","Huỳnh","Phan","Vũ","Võ","Đặng","Bùi","Đỗ","Hồ","Ngô","Dương","Lý","Đinh","Trương","Lâm","Mai"]
HO_W = [38,11,9,7,5,5,4,4,4,3,3,3,2,2,2,1,1,1,1,1]
DEM_NAM = ["Văn","Hữu","Đức","Minh","Quốc","Thanh","Công","Gia","Tuấn","Hoàng"]
DEM_NU = ["Thị","Ngọc","Thu","Thanh","Minh","Bảo","Kim","Mỹ","Phương","Hồng"]
TEN_NAM = ["An","Bình","Cường","Dũng","Đạt","Hải","Hùng","Huy","Khang","Khoa","Long","Lộc","Minh","Nam","Nghĩa","Phát","Phong","Phúc","Quân","Sơn","Tài","Thắng","Thịnh","Toàn","Trí","Trung","Tuấn","Việt","Vinh","Vũ"]
TEN_NU = ["Anh","Chi","Diệp","Dung","Giang","Hà","Hạnh","Hằng","Hiền","Hoa","Hương","Lan","Linh","Loan","Mai","My","Ngân","Ngọc","Nhung","Oanh","Phương","Quyên","Tâm","Thảo","Thư","Trang","Trinh","Uyên","Vân","Yến"]

class Gen:
    def __init__(self, seed):
        self.r = random.Random(seed)
    # ---- ngẫu nhiên cơ bản
    def pick(self, seq): return seq[self.r.randrange(len(seq))]
    def wpick(self, seq, weights): return self.r.choices(seq, weights=weights, k=1)[0]
    def chance(self, p): return self.r.random() < p
    def randint(self, a, b): return self.r.randint(a, b)
    def uniform(self, a, b, nd=1): return round(self.r.uniform(a, b), nd)
    def gauss(self, mu, sd, lo, hi, nd=1):
        x = self.r.gauss(mu, sd); return round(min(hi, max(lo, x)), nd)
    def sample(self, seq, k): return self.r.sample(seq, k)
    # ---- tên người Việt giả lập
    def person(self, gender=None):
        g = gender or self.pick("MF")
        ho = self.wpick(HO, HO_W)
        if g == "M": return f"{ho} {self.pick(DEM_NAM)} {self.pick(TEN_NAM)}", g
        return f"{ho} {self.pick(DEM_NU)} {self.pick(TEN_NU)}", g
    # ---- thời gian
    def date(self, start, end):
        d0 = dt.date.fromisoformat(start); d1 = dt.date.fromisoformat(end)
        return d0 + dt.timedelta(days=self.r.randrange((d1 - d0).days + 1))
    def timestamp(self, start, end):
        d = self.date(start, end)
        return dt.datetime(d.year, d.month, d.day, self.randint(7, 20), self.randint(0, 59), self.randint(0, 59))

class Zipf:
    """Chọn phần tử lệch theo luật Zipf: phần tử đầu danh sách được chọn nhiều nhất."""
    def __init__(self, items, s, gen):
        self.items = list(items); self.g = gen
        acc = 0.0; self.cum = []
        for k in range(1, len(self.items) + 1):
            acc += 1.0 / (k ** s); self.cum.append(acc)
    def pick(self):
        x = self.g.r.random() * self.cum[-1]
        return self.items[bisect.bisect_left(self.cum, x)]

def split_counts(total, weights, at_least=1):
    """Chia total thành các phần theo trọng số, mỗi phần ≥ at_least."""
    n = len(weights); base = [at_least] * n; rest = total - at_least * n
    raw = [rest * w / sum(weights) for w in weights]
    out = [base[i] + int(raw[i]) for i in range(n)]
    i = 0
    while sum(out) < total:
        out[i % n] += 1; i += 1
    return out

class Writer:
    def __init__(self, outdir):
        self.out = Path(outdir); self.out.mkdir(parents=True, exist_ok=True)
        self.counts = {}
    def write(self, table, columns, rows):
        with open(self.out / f"{table}.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f); w.writerow(columns); n = 0
            for row in rows:
                w.writerow(["" if v is None else (json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else
                            ("true" if v is True else "false" if v is False else v)) for v in row]); n += 1
        self.counts[table] = n
    def summary(self, info):
        info["rows"] = self.counts
        with open(self.out / "summary.json", "w", encoding="utf-8") as f:
            json.dump(info, f, ensure_ascii=False, indent=2)

def count_by(rows, idx, keys):
    d = {k: 0 for k in keys}
    for r in rows: d[r[idx]] += 1
    return d

def main_cli(generate, de, seed):
    ap = argparse.ArgumentParser(description=f"Bộ sinh dữ liệu CS5104 — Đề {de} (seed cố định {seed})")
    ap.add_argument("--size", choices=["mini", "lab"], default="lab")
    ap.add_argument("--out", default=None, help="thư mục kết quả (mặc định output/<size>)")
    a = ap.parse_args()
    out = a.out or str(Path(__file__).resolve().parent / "output" / a.size)
    w = Writer(out); info = generate(Gen(seed), a.size, w)
    info = {"de": de, "seed": seed, "size": a.size, **info}
    w.summary(info)
    print(f"Đề {de} · seed {seed} · cỡ {a.size} → {out}")
    for t, n in w.counts.items(): print(f"  {t:<26}{n:>9}")

# ======================================================================
# Đề 6 — Chuỗi khách sạn nghỉ dưỡng
# ======================================================================
DE, SEED = 6, 402738
SITES   = ["dalat", "nhatrang", "phuquoc", "danang"]
WEIGHTS = [0.20, 0.26, 0.24, 0.30]          # tỉ lệ khách sạn (và phòng) theo vùng
CROSS   = 0.07                              # tỉ lệ lượt đặt thuộc đoàn tour có phòng ở ≥ 2 vùng
TYPES, TYPE_MIX = ["tour", "business", "family"], [0.45, 0.35, 0.20]
START, END = "2025-01-01", "2026-06-30"
SIZES = {"mini": dict(room_type=4, tour_group=6, hotel=8, room=40, booking=120),
         "lab":  dict(room_type=15, tour_group=800, hotel=60, room=6000, booking=80000)}
RNAME = {"dalat": "Đà Lạt", "nhatrang": "Nha Trang", "phuquoc": "Phú Quốc", "danang": "Đà Nẵng"}
RT = [("Standard", 2), ("Superior", 2), ("Deluxe", 2), ("Family", 4), ("Suite", 3), ("Twin", 2), ("Triple", 3), ("Bungalow", 4)]
AGENCY = ["Saigontourist","Vietravel","BenThanh Tourist","Hanoitourist","TST Tourist","Lữ hành Tây Ninh"]

def generate(g, size, w):
    S = SIZES[size]
    rtypes = [(f"RT{i:02d}", f"{RT[(i-1) % len(RT)][0]}{'' if i <= len(RT) else ' ' + str((i-1)//len(RT)+1)}", RT[(i-1) % len(RT)][1]) for i in range(1, S["room_type"] + 1)]
    w.write("room_type", ["room_type_code","name","capacity"], rtypes)
    zrt = Zipf([r[0] for r in rtypes], 1.0, g)
    per = split_counts(S["hotel"], WEIGHTS, 2); hotels = []; h = 0
    for r, n in zip(SITES, per):
        for j in range(n):
            h += 1; hotels.append((h, f"Sông Tiền Resort {RNAME[r]} {j+1}", r, g.pick([3, 4, 4, 5])))
    w.write("hotel", ["hotel_id","name","region","stars"], hotels)
    reg_of_hotel = {x[0]: x[2] for x in hotels}
    rooms = []
    per_h = split_counts(S["room"], [g.uniform(0.5, 1.5, 2) for _ in hotels], 3)
    rid = 0
    for (hid, *_), n in zip(hotels, per_h):
        for k in range(n):
            rid += 1; rooms.append((rid, hid, zrt.pick(), 1 + k // 20, g.randint(8, 60) * 100_000))
    w.write("room", ["room_id","hotel_id","room_type_code","floor","rate"], rooms)
    rooms_by = {r: [x[0] for x in rooms if reg_of_hotel[x[1]] == r] for r in SITES}
    # đoàn tour: một phần đoàn đi nhiều vùng
    p_multi = min(0.9, CROSS / TYPE_MIX[0])
    groups = []; g_regions = {}
    for i in range(1, S["tour_group"] + 1):
        groups.append((i, g.pick(AGENCY), g.randint(10, 45), g.date(START, END)))
        home = g.wpick(SITES, WEIGHTS)
        g_regions[i] = [home] + (g.sample([x for x in SITES if x != home], g.randint(1, 2)) if (i == 1 or g.chance(p_multi)) else [])
    w.write("tour_group", ["tour_group_id","agency","size","start_date"], groups)
    bookings, rtour, rbus, rfam, rchild = [], [], [], [], []; tcount = {t: 0 for t in TYPES}; used = {}
    for i in range(1, S["booking"] + 1):
        t = g.wpick(TYPES, TYPE_MIX); tcount[t] += 1; tg = None
        if t == "tour":
            tg = g.randint(1, S["tour_group"]); reg = g.pick(g_regions[tg])
            d = {"group_code": f"TG{tg:04d}", "meal_plan": g.pick(["BB","HB","FB"]), "guide_room": g.chance(0.1)}
            rtour.append((i, d["group_code"], d["meal_plan"], d["guide_room"]))
            used.setdefault(tg, set()).add(reg)
        else:
            reg = g.wpick(SITES, WEIGHTS)
            if t == "business":
                d = {"company": f"Cty TNHH {g.pick(['An Phát','Minh Long','Thành Đạt','Tân Tạo','Hoà Bình'])}", "tax_code": f"03{g.randint(10000000, 99999999)}", "late_checkout": g.chance(0.3)}
                rbus.append((i, d["company"], d["tax_code"], d["late_checkout"]))
            else:
                ages = [g.randint(0, 15) for _ in range(g.randint(0, 3))]
                d = {"extra_bed": g.chance(0.4), "children_ages": ages, "airport_pickup": g.chance(0.5)}
                rfam.append((i, d["extra_bed"], d["airport_pickup"])); rchild += [(i, k + 1, a) for k, a in enumerate(ages)]
        bookings.append([i, g.pick(rooms_by[reg]), g.person()[0], g.date(START, END), g.randint(1, 7), t, tg, d])
    multi = {k for k, v in used.items() if len(v) >= 2}
    cross = sum(1 for b in bookings if b[6] in multi)
    w.write("booking", ["booking_id","room_id","guest_name","check_in","nights","guest_type","tour_group_id","request"], bookings)
    w.write("req_tour", ["booking_id","group_code","meal_plan","guide_room"], rtour)
    w.write("req_business", ["booking_id","company","tax_code","late_checkout"], rbus)
    w.write("req_family", ["booking_id","extra_bed","airport_pickup"], rfam)
    w.write("req_family_child", ["booking_id","seq","age"], rchild)
    return {"sites": SITES, "by_region": {"hotel.region": count_by(hotels, 2, SITES)},
            "cross_site": {"definition": "booking thuộc tour_group có phòng ở từ hai region trở lên", "rows": cross, "rate": round(cross / S["booking"], 4),
                           "multi_region_groups": len(multi)},
            "jsonb_types": {"booking.guest_type": tcount}}


if __name__ == "__main__":
    main_cli(generate, DE, SEED)
