"""Locust load test for civpulse geo-api.

Cold-cache run (unique addresses):
  locust -f loadtests/geo_api_locustfile.py --headless --users 30 --spawn-rate 0.25 --run-time 7m --host http://localhost:8000 --csv loadtests/reports/cold_cache --csv-full-history

Warm-cache run (repeated addresses):
  GEO_LOADTEST_WARM=1 locust -f loadtests/geo_api_locustfile.py --headless --users 30 --spawn-rate 0.25 --run-time 7m --host http://localhost:8000 --csv loadtests/reports/warm_cache --csv-full-history
"""

import os
import random
from pathlib import Path

from locust import HttpUser, between, task


ADDRESSES_DIR = Path(__file__).parent / "addresses"
ADDRESS_FILE = (
    ADDRESSES_DIR / "warm_cache_addresses.txt"
    if os.environ.get("GEO_LOADTEST_WARM")
    else ADDRESSES_DIR / "cold_cache_addresses.txt"
)
ADDRESSES = [
    line.strip()
    for line in ADDRESS_FILE.read_text(encoding="utf-8").splitlines()
    if line.strip()
]


class GeoApiUser(HttpUser):
    wait_time = between(0.5, 2.0)

    @task(5)
    def geocode(self):
        address = random.choice(ADDRESSES)
        self.client.post("/geocode", json={"address": address})

    @task(3)
    def validate(self):
        address = random.choice(ADDRESSES)
        self.client.post("/validate", json={"address": address})

    @task(2)
    def cascade_trace(self):
        address = random.choice(ADDRESSES)
        self.client.post(
            "/geocode",
            json={"address": address},
            params={"trace": "true"},
        )
