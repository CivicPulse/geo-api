import pytest


pytestmark = pytest.mark.e2e

GEOCODE_PROVIDERS = [
    "census",
    "openaddresses",
    "postgis_tiger",
    "national_address_database",
    "macon_bibb",
]


@pytest.mark.parametrize("provider_name", GEOCODE_PROVIDERS)
async def test_geocode_provider(e2e_client, provider_addresses, provider_name):
    address = provider_addresses[provider_name]["geocode_address"]

    resp = await e2e_client.post("/geocode", json={"address": address})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["address_hash"]

    all_results = body["results"] + body.get("local_results", [])
    providers = [result["provider_name"] for result in all_results]
    assert provider_name in providers, (
        f"Expected provider {provider_name!r} in response for {address!r}; "
        f"got providers={providers!r}"
    )


async def test_geocode_returns_coordinates(e2e_client, provider_addresses):
    address = provider_addresses["census"]["geocode_address"]

    resp = await e2e_client.post("/geocode", json={"address": address})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    all_results = body["results"] + body.get("local_results", [])
    assert any(
        isinstance(result.get("latitude"), (int, float))
        and isinstance(result.get("longitude"), (int, float))
        for result in all_results
    ), f"No coordinates returned for {address!r}: {body!r}"
