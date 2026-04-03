import os
from pathlib import Path

import httpx
import pytest
import yaml


FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
async def e2e_client():
    base_url = os.environ.get("GEO_API_BASE_URL", "http://localhost:8000")
    async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
        yield client


@pytest.fixture(scope="session")
def provider_addresses():
    fixture_path = FIXTURES_DIR / "provider_addresses.yaml"
    with fixture_path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)
