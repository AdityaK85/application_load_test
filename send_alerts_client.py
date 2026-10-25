import asyncio, aiohttp, time, statistics
from datetime import datetime, timezone
from pathlib import Path
from collections import Counter

# BASE = "http://192.168.56.110/api"
BASE = "http://127.0.0.1:8000/api"
USERNAME, PASSWORD = "admin", "admin123"
IMAGE_PATH = r"C:\Users\HP\Downloads\detection_561.jpg"

TOTAL = 1000     # number of users clicking at the same moment
TIMEOUT = 30     # seconds to wait for each response

async def login(session):
    async with session.post(f"{BASE}/auth/login/",
                            data={"username": USERNAME, "password": PASSWORD}) as r:
        r.raise_for_status()
        return (await r.json())["access"]

async def user(session, token, img, i, gate, results):
    # Build the request BEFORE the gate, so nothing slow happens after release
    form = aiohttp.FormData()
    form.add_field("image", img, filename=f"d_{i}.jpg", content_type="image/jpeg")
    form.add_field("alert_names", "person")
    form.add_field("alert_names", "vehicle")
    form.add_field("camera_no", "CAM-1")
    form.add_field("alert_time", datetime.now(timezone.utc).isoformat())
    headers = {"Authorization": f"Bearer {token}"}

    await gate.wait()                      # all 1000 wait here until released
    t = time.perf_counter()
    try:
        async with session.post(f"{BASE}/alerts/", headers=headers, data=form) as r:
            await r.read()
            results.append((r.status, (time.perf_counter() - t) * 1000, ""))
    except asyncio.TimeoutError:
        results.append(("TIMEOUT", (time.perf_counter() - t) * 1000, "no response in time"))
    except aiohttp.ClientConnectorError as e:
        results.append(("CONN_REFUSED", (time.perf_counter() - t) * 1000, str(e)[:100]))
    except Exception as e:
        results.append(("CONN_DROPPED", (time.perf_counter() - t) * 1000, type(e).__name__ + ": " + str(e)[:100]))

async def main():
    img = Path(IMAGE_PATH).read_bytes()
    conn = aiohttp.TCPConnector(limit=0)   # no client-side connection limit
    async with aiohttp.ClientSession(connector=conn,
                                     timeout=aiohttp.ClientTimeout(total=TIMEOUT)) as s:
        token = await login(s)
        gate, results = asyncio.Event(), []

        tasks = [asyncio.create_task(user(s, token, img, i, gate, results))
                 for i in range(TOTAL)]
        await asyncio.sleep(1)             # let all tasks get ready at the gate

        print(f"Firing {TOTAL} requests at the same instant...")
        start = time.perf_counter()
        gate.set()                         # release everyone at once
        await asyncio.gather(*tasks)
        total_time = time.perf_counter() - start

    accepted = [r for r in results if isinstance(r[0], int) and 200 <= r[0] < 300]
    rejected = [r for r in results if r not in accepted]
    lat = sorted(r[1] for r in results)
    pct = lambda p: lat[min(len(lat) - 1, int(len(lat) * p))]

    print("=" * 55)
    print(f"Total fired      : {TOTAL}")
    print(f"ACCEPTED (2xx)   : {len(accepted)}  ({len(accepted)/TOTAL*100:.1f}%)")
    print(f"REJECTED/FAILED  : {len(rejected)}  ({len(rejected)/TOTAL*100:.1f}%)")
    print(f"Time for all     : {total_time:.2f}s")
    print(f"Latency avg/p50/p95/max : {statistics.mean(lat):.0f} / {pct(.5):.0f} / {pct(.95):.0f} / {lat[-1]:.0f} ms")
    print("\nBreakdown:")
    for k, c in sorted(Counter(r[0] for r in results).items(), key=lambda x: str(x[0])):
        print(f"  {str(k):<14} {c}")
    errs = Counter(r[2] for r in rejected if r[2])
    if errs:
        print("\nTop error reasons:")
        for msg, c in errs.most_common(5):
            print(f"  {c:>5} x {msg}")

asyncio.run(main())