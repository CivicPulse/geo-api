"""Valhalla routing sidecar reachability probe (ROUTE-01, ROUTE-02)."""
import httpx


async def _valhalla_reachable(
    base_url: str,
    http_client: httpx.AsyncClient,
    timeout_s: float = 2.0,
) -> bool:
    """HTTP probe — GET {base_url}/status with 2s timeout.

    Returns True on HTTP 200, False on any error (network, timeout, non-200).
    Used by main.py lifespan to set app.state.valhalla_enabled.
    """
    url = f"{base_url.rstrip('/')}/status"
    try:
        response = await http_client.get(url, timeout=timeout_s)
        return response.status_code == 200
    except Exception:
        return False
