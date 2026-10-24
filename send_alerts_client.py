"""
Sample client: logs in, then continuously sends images with alerts.
Usage: pip install requests ; python send_alerts_client.py
"""
import time
from datetime import datetime, timezone

import requests

BASE = "http://localhost:8000/api"
USERNAME, PASSWORD = "admin", "admin123"


def login():
    r = requests.post(f"{BASE}/auth/login/", data={"username": USERNAME, "password": PASSWORD})
    r.raise_for_status()
    return r.json()  # {"access": "...", "refresh": "..."}


def refresh(refresh_token):
    r = requests.post(f"{BASE}/auth/refresh/", data={"refresh": refresh_token})
    r.raise_for_status()
    return r.json()["access"]


def send_alert(access, image_path, names, camera_no):
    with open(image_path, "rb") as f:
        return requests.post(
            f"{BASE}/alerts/",
            headers={"Authorization": f"Bearer {access}"},
            files={"image": f},
            data={
                "alert_names": names,                      # list -> sent as repeated fields
                "camera_no": camera_no,
                "alert_time": datetime.now(timezone.utc).isoformat(),
            },
        )


if __name__ == "__main__":
    tokens = login()
    access, refresh_token = tokens["access"], tokens["refresh"]
    while True:
        r = send_alert(access, "sample.jpg", ["person", "vehicle"], "CAM-1")
        if r.status_code == 401:                 # access token expired (1 hour)
            access = refresh(refresh_token)
            continue
        print(r.status_code, r.text)
        time.sleep(2)
