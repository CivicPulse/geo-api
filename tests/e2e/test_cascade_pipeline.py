import pytest


pytestmark = pytest.mark.e2e


async def test_cascade_resolves_degraded_input(e2e_client, provider_addresses):
    degraded_address = provider_addresses["cascade_test"]["degraded_address"]

    resp = await e2e_client.post(
        "/geocode",
        json={"address": degraded_address},
        params={"trace": "true"},
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["cascade_trace"], f"Missing cascade_trace for {degraded_address!r}: {body!r}"

    stage_names = [stage["stage"] for stage in body["cascade_trace"]]
    assert stage_names, f"No cascade stages recorded for {degraded_address!r}: {body!r}"
    assert body["results"] or body.get("local_results"), (
        f"No provider results returned for {degraded_address!r}: {body!r}"
    )


async def test_cascade_dry_run_shows_would_set_official(e2e_client, provider_addresses):
    address = provider_addresses["census"]["geocode_address"]

    resp = await e2e_client.post(
        "/geocode",
        json={"address": address},
        params={"trace": "true", "dry_run": "true"},
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body.get("would_set_official") is not None or body.get("official") is not None, (
        f"Dry-run did not report an official candidate for {address!r}: {body!r}"
    )
