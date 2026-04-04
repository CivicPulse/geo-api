"""Tile server sidecar reachability probe (INFRA-05)."""
import httpx


async def _tile_server_reachable(
    base_url: str,
    http_client: httpx.AsyncClient,
    timeout_s: float = 2.0,
) -> bool:
    """HTTP probe — GET {base_url}/tile/0/0/0.png with configurable timeout.

    Returns True if the tile server responds with 200 (tile rendered) OR 404
    (tile server up but 0/0/0 not yet in DB). Returns False on network error,
    timeout, or 5xx. Tile server has no /status endpoint, so we probe the
    world-tile route which exists once the server is running.
    """
    url = f"{base_url.rstrip('/')}/tile/0/0/0.png"
    try:
        response = await http_client.get(url, timeout=timeout_s)
        return response.status_code in (200, 404)
    except Exception:
        return False
