
import asyncio
import aiohttp
import time
import statistics
from datetime import datetime, timezone
from pathlib import Path

# ================= CONFIGURATION =================

BASE = "http://localhost:8000/api"

USERNAME = "admin"
PASSWORD = "admin123"

IMAGE_PATH = "/home/appsdamin/application/detection_561.jpg"

TOTAL_REQUESTS = 1000
CONCURRENCY = 1000

ALERT_NAMES = ["person", "vehicle"]
CAMERA_NO = "CAM-1"

TIMEOUT = 60

# =================================================


async def login(session):
    async with session.post(
        f"{BASE}/auth/login/",
        data={
            "username": USERNAME,
            "password": PASSWORD
        }
    ) as response:

        response.raise_for_status()
        tokens = await response.json()

        return tokens["access"]


async def send_alert(session, access_token, image_bytes, request_id):

    start = time.perf_counter()

    try:
        form = aiohttp.FormData()

        form.add_field(
            "image",
            image_bytes,
            filename=f"detection_{request_id}.jpg",
            content_type="image/jpeg"
        )

        for name in ALERT_NAMES:
            form.add_field("alert_names", name)

        form.add_field("camera_no", CAMERA_NO)

        form.add_field(
            "alert_time",
            datetime.now(timezone.utc).isoformat()
        )

        headers = {
            "Authorization": f"Bearer {access_token}"
        }

        async with session.post(
            f"{BASE}/alerts/",
            headers=headers,
            data=form
        ) as response:

            body = await response.text()

            latency = (time.perf_counter() - start) * 1000

            return {
                "id": request_id,
                "status": response.status,
                "latency": latency,
                "error": None if response.status < 400 else body[:300]
            }

    except Exception as exc:

        latency = (time.perf_counter() - start) * 1000

        return {
            "id": request_id,
            "status": 0,
            "latency": latency,
            "error": str(exc)
        }


async def main():

    image_bytes = Path(IMAGE_PATH).read_bytes()

    connector = aiohttp.TCPConnector(
        limit=CONCURRENCY,
        limit_per_host=CONCURRENCY
    )

    timeout = aiohttp.ClientTimeout(total=TIMEOUT)

    async with aiohttp.ClientSession(
        connector=connector,
        timeout=timeout
    ) as session:

        print("Authenticating...")

        access_token = await login(session)

        print("Authentication successful")
        print(f"Total requests: {TOTAL_REQUESTS}")
        print(f"Concurrency: {CONCURRENCY}")
        print("Starting load test...\n")

        start_time = time.perf_counter()

        tasks = [
            send_alert(
                session,
                access_token,
                image_bytes,
                i
            )
            for i in range(TOTAL_REQUESTS)
        ]

        results = await asyncio.gather(*tasks)

        total_time = time.perf_counter() - start_time

    # ================= RESULTS =================

    successful = [
        r for r in results
        if 200 <= r["status"] < 300
    ]

    failed = [
        r for r in results
        if r["status"] == 0 or r["status"] >= 400
    ]

    latencies = sorted(r["latency"] for r in results)

    def percentile(values, p):
        if not values:
            return 0
        index = int((len(values) - 1) * p)
        return values[index]

    print("\n========== LOAD TEST RESULTS ==========")

    print(f"Total requests    : {TOTAL_REQUESTS}")
    print(f"Successful        : {len(successful)}")
    print(f"Failed            : {len(failed)}")

    print(f"Total time        : {total_time:.3f} seconds")
    print(f"Throughput        : {TOTAL_REQUESTS / total_time:.2f} req/sec")

    print(f"Average latency   : {statistics.mean(latencies):.2f} ms")
    print(f"P50 latency       : {percentile(latencies, 0.50):.2f} ms")
    print(f"P95 latency       : {percentile(latencies, 0.95):.2f} ms")
    print(f"P99 latency       : {percentile(latencies, 0.99):.2f} ms")

    print("\nHTTP STATUS COUNTS:")

    for status in sorted(set(r["status"] for r in results)):
        count = sum(1 for r in results if r["status"] == status)
        print(f"{status}: {count}")

    print("\nFAILED REQUESTS:")

    for result in failed[:10]:
        print(result)

    print("\n=======================================")


if __name__ == "__main__":
    asyncio.run(main())
