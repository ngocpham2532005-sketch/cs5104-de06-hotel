#!/usr/bin/env python3
"""Proxy TCP thêm trễ cố định cho chiều trả về (trạm xa -> trạm trung tâm), mô phỏng `tc netem delay`.

Phương án DỰ PHÒNG cho `make delay-on` khi không dùng được tc trong container
(DELAY_MODE=proxy, xem tools/delay.py). Chỉ dùng thư viện chuẩn.

    python tools/latency_proxy.py --delay 30 5534:127.0.0.1:5434 5535:192.168.100.198:5435

Mỗi gói nhận từ trạm xa được giữ đúng `delay` ms tính từ lúc nhận rồi mới chuyển tiếp (giữ thứ tự,
không làm giảm thông lượng) => mỗi vòng khứ hồi chậm thêm đúng `delay` ms, như netem trên một chiều.
(Ý tưởng lấy từ bản thử nghiệm của thành viên nhóm, chỉnh lại cho cấu trúc của repo này.)
"""
import argparse
import asyncio
import time


async def pipe(reader, writer, delay: float):
    q: asyncio.Queue = asyncio.Queue()

    async def sender():
        while True:
            ts, data = await q.get()
            if data is None:
                break
            wait = ts + delay - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            writer.write(data)
            await writer.drain()
        writer.close()

    task = asyncio.create_task(sender())
    try:
        while data := await reader.read(65536):
            await q.put((time.monotonic(), data))
    finally:
        await q.put((0, None))
        await task


async def handle(cr, cw, host: str, port: int, delay: float):
    try:
        sr, sw = await asyncio.open_connection(host, port)
    except OSError:
        cw.close()
        return
    await asyncio.gather(pipe(cr, sw, 0), pipe(sr, cw, delay), return_exceptions=True)


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--delay", type=float, default=30, help="ms")
    ap.add_argument("--bind", default="0.0.0.0")
    ap.add_argument("routes", nargs="+", help="cổng_nghe:máy_đích:cổng_đích")
    a = ap.parse_args()
    servers = []
    for r in a.routes:
        lp, th, tp = r.split(":")
        servers.append(await asyncio.start_server(
            lambda cr, cw, th=th, tp=int(tp): handle(cr, cw, th, tp, a.delay / 1000), a.bind, int(lp)))
        print(f"proxy :{lp} -> {th}:{tp} (+{a.delay:g} ms)", flush=True)
    await asyncio.gather(*(s.serve_forever() for s in servers))


if __name__ == "__main__":
    asyncio.run(main())
