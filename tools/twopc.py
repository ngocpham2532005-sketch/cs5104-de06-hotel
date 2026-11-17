#!/usr/bin/env python3
"""PHẦN MỞ RỘNG E2 (ngoài yêu cầu đề) — cam kết hai pha có nhật ký điều phối bền vững + phục hồi.

Bảng sao chép `tour_group` có ở cả 4 trạm, nên thêm một đoàn mới = ghi 4 bản sao một cách nguyên tử (2PC, Chương 4).
Bản cơ bản (giao diện cũ) không ghi lại quyết định của bộ điều phối: nếu bộ điều phối chết sau PREPARE thì không ai
biết nên COMMIT hay ROLLBACK các giao dịch lưỡng lự. Bản này:

  1. ghi `begin` vào nhật ký (fsync)                     — gid, các trạm tham gia, dòng sẽ ghi
  2. pha 1: mọi trạm INSERT + PREPARE TRANSACTION
  3. ghi `commit` vào nhật ký (fsync)  ← ĐIỂM CAM KẾT     — từ đây giao dịch chắc chắn được cam kết
  4. pha 2: COMMIT PREPARED ở từng trạm; trạm nào lỗi thì để lại, KHÔNG rollback (đã quyết định commit)
  5. ghi `end` khi mọi trạm đã xong
Phục hồi (presumed abort): giao dịch lưỡng lự có `commit` trong nhật ký -> COMMIT PREPARED; không có -> ROLLBACK PREPARED.

    python tools/twopc.py create  [--agency A] [--size N] [--start YYYY-MM-DD] [--crash prepare|decision|mid-commit]
    python tools/twopc.py status            # giao dịch lưỡng lự ở từng trạm + quyết định trong nhật ký + thử khoá
    python tools/twopc.py recover [--force] # giải quyết giao dịch lưỡng lự theo nhật ký

--crash giả lập bộ điều phối chết (os._exit) ngay SAU bước tương ứng: prepare (sau pha 1, trước điểm cam kết),
decision (sau điểm cam kết, chưa COMMIT trạm nào), mid-commit (đã COMMIT một trạm, các trạm khác chưa).
Nhật ký: results/2pc_coordinator.jsonl (máy A).
"""
from __future__ import annotations

import argparse
import json
import os
import time
from datetime import date
from functools import partial

from common import RESULTS, SITES_ORDER, Config

LOG = RESULTS / "2pc_coordinator.jsonl"
FORMAT_ID = 1
say_ = partial(print, flush=True)   # os._exit không xả bộ đệm stdout -> luôn flush
STALE_S = 10      # recover không tự rollback giao dịch chưa có quyết định nếu mới PREPARE < 10 s (có thể đang chạy)


class TwoPCError(RuntimeError):
    pass


# ------------------------------------------------------------------ nhật ký bền vững
def _log_write(rec: dict):
    RESULTS.mkdir(exist_ok=True)
    rec = dict(rec, ts=time.time(), t=time.strftime("%H:%M:%S"))
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
        f.flush()
        os.fsync(f.fileno())          # quyết định phải nằm trên đĩa TRƯỚC khi gửi COMMIT PREPARED


def log_read() -> dict[str, dict]:
    """gid -> {"row":…, "sites":…, "phase": begin|commit|abort|end}"""
    out: dict[str, dict] = {}
    if not LOG.exists():
        return out
    for line in LOG.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue                  # dòng cuối ghi dở khi chết giữa chừng
        g = out.setdefault(r["gid"], {})
        if r["phase"] == "begin":
            g.update(row=r["row"], sites=r["sites"])
        g["phase"] = r["phase"]
    return out


def decided_commit(info: dict | None) -> bool:
    return bool(info) and info.get("phase") in ("commit", "end")


# ------------------------------------------------------------------ giao dịch
def _crash(point: str, crash: str | None, say):
    if crash == point:
        say(f"💥 GIẢ LẬP bộ điều phối chết sau bước '{point}' (os._exit) — xem: make ext-2pc-status")
        os._exit(3)


def create_tour_group(cfg: Config, agency: str, size: int, start: date, crash: str | None = None,
                      say=say_, durable: bool = True) -> tuple[int, list[str]]:
    """Tạo đoàn mới ở mọi trạm. Trả (tour_group_id, các trạm còn chờ COMMIT PREPARED).
    durable=False: bỏ nhật ký điều phối (= 2PC bản cơ bản) — chỉ dùng để make ext-bench đo chi phí nhật ký."""
    import psycopg
    log_write = _log_write if durable else (lambda rec: None)
    conns: dict[str, psycopg.Connection] = {}
    prepared: list[str] = []
    gid = None
    try:
        for s in SITES_ORDER:
            try:
                conns[s] = cfg.connect(s, timeout=2, autocommit=False)
            except psycopg.OperationalError as e:
                raise TwoPCError(f"trạm {s} mất kết nối — huỷ trước pha 1, không trạm nào được ghi") from e
        new_id = conns[cfg.central].execute("SELECT nextval('tour_group_id_seq')").fetchone()[0]
        conns[cfg.central].rollback()
        gid = f"tg{new_id}"
        row = [new_id, agency, int(size), str(start)]
        log_write({"gid": gid, "phase": "begin", "sites": SITES_ORDER, "row": row})
        say(f"nhật ký: begin {gid} (fsync)")
        # ---- pha 1
        for s in SITES_ORDER:
            c = conns[s]
            c.tpc_begin(c.xid(FORMAT_ID, gid, s))
            c.execute("INSERT INTO tour_group VALUES (%s, %s, %s, %s)", row)
            c.tpc_prepare()
            prepared.append(s)
            say(f"PREPARE TRANSACTION @ {s} ✓")
    except Exception as e:  # noqa: BLE001 — bất kỳ lỗi nào ở pha 1 -> huỷ
        if gid:
            log_write({"gid": gid, "phase": "abort", "reason": str(e)[:200]})
            say(f"nhật ký: abort {gid}")
        for s in prepared:
            try:
                conns[s].tpc_rollback()
                say(f"ROLLBACK PREPARED @ {s}")
            except psycopg.Error:
                say(f"ROLLBACK PREPARED @ {s} chưa được (trạm mất) — make ext-2pc-recover sẽ huỷ sau")
        for c in conns.values():
            c.close()
        raise TwoPCError(str(e)) from e
    _crash("prepare", crash, say)
    # ---- điểm cam kết
    log_write({"gid": gid, "phase": "commit"})
    say(f"nhật ký: commit {gid} (fsync) — ĐIỂM CAM KẾT")
    _crash("decision", crash, say)
    # ---- pha 2: không bao giờ rollback nữa; trạm lỗi để lại cho recover
    pending = []
    for i, s in enumerate(prepared):
        try:
            conns[s].tpc_commit()
            say(f"COMMIT PREPARED @ {s} ✓")
        except psycopg.Error as e:
            pending.append(s)
            say(f"COMMIT PREPARED @ {s} CHƯA ĐƯỢC ({str(e).strip()[:80]}) — giữ lưỡng lự, recover sẽ commit")
        if i == 0:
            _crash("mid-commit", crash, say)
    for c in conns.values():
        c.close()
    mirror_ref(cfg, row, say)
    if not pending:
        log_write({"gid": gid, "phase": "end"})
    return new_id, pending


def mirror_ref(cfg: Config, row: list, say=say_):
    """CSDL đối chứng (công cụ chấm, không phải một trạm) nhận dòng khi quyết định là commit."""
    try:
        with cfg.connect("ref") as r:
            r.execute("INSERT INTO tour_group VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING", row)
    except Exception as e:  # noqa: BLE001
        say(f"chưa chép được sang ref: {e}")


# ------------------------------------------------------------------ trạng thái / phục hồi
def in_doubt(cfg: Config) -> dict[str, list | None]:
    """trạm -> [(xid, tuổi tính bằng giây)] của giao dịch 2PC tạo đoàn còn lưỡng lự; None nếu trạm mất kết nối."""
    out: dict[str, list | None] = {}
    for s in SITES_ORDER:
        try:
            c = cfg.connect(s, timeout=2, autocommit=False)
        except Exception:  # noqa: BLE001
            out[s] = None
            continue
        with c:
            now = c.execute("SELECT now()").fetchone()[0]
            c.rollback()
            out[s] = [(x, (now - x.prepared).total_seconds()) for x in c.tpc_recover()
                      if x.format_id == FORMAT_ID and str(x.gtrid).startswith("tg")]
    return out


def status(cfg: Config):
    book = log_read()
    found = in_doubt(cfg)
    total = 0
    print(f"Nhật ký bộ điều phối: {LOG.relative_to(RESULTS.parent)} ({len(book)} giao dịch)")
    for s, items in found.items():
        if items is None:
            print(f"  {s:<9} MẤT KẾT NỐI (không biết có giao dịch lưỡng lự hay không)")
            continue
        total += len(items)
        print(f"  {s:<9} {len(items)} giao dịch lưỡng lự")
        for x, age in items:
            info = book.get(x.gtrid)
            dec = info["phase"] if info else "không có trong nhật ký"
            print(f"            {x.gtrid:<10} prepared {age:6.1f} s trước · nhật ký: {dec} -> recover sẽ "
                  f"{'COMMIT' if decided_commit(info) else 'ROLLBACK'}")
    for gid, info in book.items():
        row = info.get("row")
        if not row:
            continue
        seen = []
        for s in SITES_ORDER:
            if found.get(s) is None:
                continue
            with cfg.connect(s, timeout=2) as c:
                if c.execute("SELECT 1 FROM tour_group WHERE tour_group_id = %s", [row[0]]).fetchone():
                    seen.append(s)
        if info["phase"] in ("begin", "commit") or 0 < len(seen) < len(SITES_ORDER):
            print(f"  {gid}: nhật ký = {info['phase']} · đã thấy ở {seen or 'không trạm nào'}"
                  + ("  ⚠ bản sao KHÔNG nhất quán giữa các trạm" if 0 < len(seen) < len(SITES_ORDER) else ""))
    if total:
        probe_lock(cfg, found)
    else:
        print("Không có giao dịch lưỡng lự." if all(v is not None for v in found.values()) else "")


def probe_lock(cfg: Config, found):
    """Cho thấy 'chặn' của 2PC: thêm lại đúng tour_group_id đang lưỡng lự sẽ phải chờ khoá của giao dịch đã PREPARE."""
    s = next(s for s, v in found.items() if v)
    tg = int(found[s][0][0].gtrid[2:])
    with cfg.connect(s, timeout=2, autocommit=False) as c:
        c.execute("SET LOCAL lock_timeout = '700ms'")
        try:
            c.execute("INSERT INTO tour_group VALUES (%s, 'probe', 1, DATE '2025-01-01')", [tg])
            print(f"  thử INSERT tour_group_id={tg} @ {s}: không bị chặn (?)")
        except Exception as e:  # noqa: BLE001
            print(f"  thử INSERT tour_group_id={tg} @ {s}: BỊ CHẶN bởi giao dịch đã PREPARE -> {str(e).strip().splitlines()[0]}")
        c.rollback()


def recover(cfg: Config, force: bool = False, say=say_) -> dict:
    book = log_read()
    found = in_doubt(cfg)
    done = {"commit": 0, "rollback": 0, "skip": 0, "unreachable": [s for s, v in found.items() if v is None]}
    for s, items in found.items():
        if not items:
            continue
        with cfg.connect(s, timeout=2, autocommit=False) as c:
            for x, age in items:
                info = book.get(x.gtrid)
                if decided_commit(info):
                    c.tpc_commit(x)
                    done["commit"] += 1
                    say(f"COMMIT PREPARED   {x.gtrid} @ {s}   (nhật ký: commit)")
                elif info and info.get("phase") == "begin" and age < STALE_S and not force:
                    done["skip"] += 1
                    say(f"bỏ qua           {x.gtrid} @ {s}   (mới PREPARE {age:.0f} s, có thể bộ điều phối đang chạy; --force)")
                else:
                    c.tpc_rollback(x)
                    done["rollback"] += 1
                    say(f"ROLLBACK PREPARED {x.gtrid} @ {s}   (nhật ký: {info['phase'] if info else 'không có'} "
                        f"-> presumed abort)")
    # đánh dấu end cho giao dịch đã commit mà không còn trạm nào lưỡng lự
    if not done["unreachable"]:
        left = in_doubt(cfg)
        still = {x.gtrid for v in left.values() for x, _ in (v or [])}
        for gid, info in book.items():
            if info.get("phase") == "commit" and gid not in still:
                mirror_ref(cfg, info["row"], say)
                _log_write({"gid": gid, "phase": "end", "by": "recover"})
            elif info.get("phase") == "begin" and gid not in still:
                _log_write({"gid": gid, "phase": "abort", "by": "recover"})
    if done["unreachable"]:
        say(f"⚠ chưa kiểm được {done['unreachable']} (mất kết nối) — chạy lại recover khi trạm sống lại")
    say(f"Xong: {done['commit']} commit, {done['rollback']} rollback, {done['skip']} bỏ qua.")
    return done


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create")
    c.add_argument("--agency", default="Vietravel")
    c.add_argument("--size", type=int, default=20)
    c.add_argument("--start", type=date.fromisoformat, default=date(2025, 8, 1))
    c.add_argument("--crash", choices=["prepare", "decision", "mid-commit"])
    sub.add_parser("status")
    r = sub.add_parser("recover")
    r.add_argument("--force", action="store_true")
    a = ap.parse_args()
    cfg = Config()
    if a.cmd == "create":
        tg, pending = create_tour_group(cfg, a.agency, a.size, a.start, a.crash)
        print(f"Đoàn TG{tg:04d} (tour_group_id = {tg})" + (f" — còn chờ ở {pending}" if pending else " ở cả 4 trạm"))
    elif a.cmd == "status":
        status(cfg)
    else:
        recover(cfg, a.force)


if __name__ == "__main__":
    main()
