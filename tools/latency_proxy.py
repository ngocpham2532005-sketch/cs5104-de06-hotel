"""
Proxy TCP thêm độ trễ cố định cho chiều trả về (server -> client), mô phỏng `tc netem delay`.
Dùng làm PHƯƠNG ÁN DỰ PHÒNG cho `make delay-on` khi không dùng được tc (DELAY_MODE=proxy),
và để thử nghiệm trên một máy.

  python3 tools/latency_proxy.py --delay 30 5535:192.168.1.20:5435 5536:192.168.1.20:5436
"""
import argparse, asyncio, time


async def pipe(reader, writer, delay):
    q = asyncio.Queue()

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
        while True:
            data = await reader.read(65536)
            if not data:
                break
            await q.put((time.monotonic(), data))
    finally:
        await q.put((0, None))
        await task


async def handle(cr, cw, host, port, delay):
    try:
        sr, sw = await asyncio.open_connection(host, port)
    except OSError:
        cw.close(); return
    await asyncio.gather(pipe(cr, sw, 0), pipe(sr, cw, delay), return_exceptions=True)


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--delay", type=float, default=30, help="ms")
    ap.add_argument("--bind", default="0.0.0.0")
    ap.add_argument("routes", nargs="+", help="listen_port:target_host:target_port")
    a = ap.parse_args()
    servers = []
    for r in a.routes:
        lp, th, tp = r.split(":")
        servers.append(await asyncio.start_server(
            lambda cr, cw, th=th, tp=int(tp): handle(cr, cw, th, tp, a.delay / 1000), a.bind, int(lp)))
        print(f"proxy :{lp} -> {th}:{tp} (+{a.delay} ms)", flush=True)
    await asyncio.gather(*(s.serve_forever() for s in servers))


if __name__ == "__main__":
    asyncio.run(main())
