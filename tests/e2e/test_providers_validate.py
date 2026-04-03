import pytest


pytestmark = pytest.mark.e2e

VALIDATE_PROVIDERS = [
    "openaddresses",
    "postgis_tiger",
    "national_address_database",
    "macon_bibb",
]


@pytest.mark.parametrize("provider_name", VALIDATE_PROVIDERS)
async def test_validate_provider(e2e_client, provider_addresses, provider_name):
    address = provider_addresses[provider_name]["validate_address"]

    resp = await e2e_client.post("/validate", json={"address": address})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["candidates"], f"No candidates returned for {address!r}: {body!r}"

    all_candidates = body["candidates"] + body.get("local_candidates", [])
    candidate_providers = [candidate["provider_name"] for candidate in all_candidates]
    assert provider_name in candidate_providers, (
        f"Expected provider {provider_name!r} in validation response for {address!r}; "
        f"got providers={candidate_providers!r}"
    )
