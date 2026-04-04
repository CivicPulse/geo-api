"""Nominatim geocoding provider adapter.

Implements GeocodingProvider using the OSM Nominatim geocoding API:
https://nominatim.org/release-docs/latest/api/Search/

Key facts about the Nominatim API:
- No API key required (when self-hosted)
- Uses OSM data — accuracy varies by OSM data quality
- Returns `importance` field (0.0–1.0) which is used as confidence
- Coordinates returned as strings — must be converted to float
- On no match: returns empty list []
- Transport URL: settings.osm_nominatim_url (default: http://nominatim:8080)
"""
import httpx

from civpulse_geo.config import settings
from civpulse_geo.providers.base import GeocodingProvider
from civpulse_geo.providers.exceptions import ProviderNetworkError
from civpulse_geo.providers.schemas import GeocodingResult

NOMINATIM_SEARCH_PATH = "/search"
NOMINATIM_DEFAULT_CONFIDENCE = 0.70
NOMINATIM_NO_MATCH_CONFIDENCE = 0.0
NOMINATIM_NO_MATCH_LOCATION_TYPE = "NO_MATCH"

# Maps OSM type strings to the project's LocationType values.
# Nominatim /search returns a "type" field indicating the OSM object type.
# Missing/unknown types fall back to "GEOMETRIC_CENTER".
OSM_TYPE_TO_LOCATION_TYPE: dict[str, str] = {
    "house": "ROOFTOP",
    "building": "ROOFTOP",
    "address": "ROOFTOP",
    "way": "GEOMETRIC_CENTER",
    "street": "GEOMETRIC_CENTER",
    "node": "GEOMETRIC_CENTER",
    "relation": "APPROXIMATE",
    "city": "APPROXIMATE",
    "suburb": "APPROXIMATE",
    "administrative": "APPROXIMATE",
}


class NominatimGeocodingProvider(GeocodingProvider):
    """Geocoding provider backed by the OSM Nominatim geocoding service.

    Nominatim is a free, self-hosted geocoder based on OpenStreetMap data.
    It is configured via ``settings.osm_nominatim_url``.

    Confidence is derived from the ``importance`` field in the Nominatim
    response, clamped to [0.0, 1.0]. When importance is missing, the
    default confidence of 0.70 is used.

    Location type is derived from the ``type`` field in the Nominatim response
    via ``OSM_TYPE_TO_LOCATION_TYPE``. Unknown types map to "GEOMETRIC_CENTER".

    Args:
        http_client: Optional pre-configured httpx.AsyncClient for testing.
            If not provided, a new client is created per request.
    """

    def __init__(self, http_client: httpx.AsyncClient | None = None) -> None:
        self._client = http_client

    @property
    def provider_name(self) -> str:
        return "nominatim"

    async def geocode(
        self,
        address: str,
        *,
        http_client: httpx.AsyncClient | None = None,
    ) -> GeocodingResult:
        """Geocode a single freeform address using the Nominatim /search endpoint.

        Calls ``{osm_nominatim_url}/search?q={address}&format=json&limit=1``
        and maps the first result to a GeocodingResult.

        Args:
            address: Freeform address string.
            http_client: Optional override client for this call (e.g., in tests).

        Returns:
            GeocodingResult with lat/lng, location_type, confidence, and raw_response.
            Returns NO_MATCH result (lat=0.0, lng=0.0, confidence=0.0) when Nominatim
            returns an empty list.

        Raises:
            ProviderNetworkError: Nominatim is unreachable or returned an HTTP error.
        """
        client = http_client or self._client
        base_url = settings.osm_nominatim_url.rstrip("/")
        url = f"{base_url}{NOMINATIM_SEARCH_PATH}"
        params = {
            "q": address,
            "format": "json",
            "limit": 1,
        }

        try:
            if client is not None:
                response = await client.get(url, params=params)
            else:
                async with httpx.AsyncClient() as auto_client:
                    response = await auto_client.get(url, params=params)
            response.raise_for_status()
        except httpx.RequestError as exc:
            raise ProviderNetworkError(
                f"Nominatim unreachable: {exc}"
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise ProviderNetworkError(
                f"Nominatim HTTP error {exc.response.status_code}: {exc}"
            ) from exc

        raw: list[dict] = response.json()

        if not raw:
            return GeocodingResult(
                lat=0.0,
                lng=0.0,
                location_type=NOMINATIM_NO_MATCH_LOCATION_TYPE,
                confidence=NOMINATIM_NO_MATCH_CONFIDENCE,
                raw_response={},
                provider_name=self.provider_name,
            )

        match = raw[0]
        lat = float(match["lat"])
        lng = float(match["lon"])

        # Clamp importance to [0.0, 1.0]; fall back to NOMINATIM_DEFAULT_CONFIDENCE
        raw_importance = match.get("importance", NOMINATIM_DEFAULT_CONFIDENCE)
        try:
            confidence = float(raw_importance)
        except (TypeError, ValueError):
            confidence = NOMINATIM_DEFAULT_CONFIDENCE
        confidence = max(0.0, min(1.0, confidence))

        osm_type = match.get("type", "")
        location_type = OSM_TYPE_TO_LOCATION_TYPE.get(osm_type, "GEOMETRIC_CENTER")

        return GeocodingResult(
            lat=lat,
            lng=lng,
            location_type=location_type,
            confidence=confidence,
            raw_response=match,
            provider_name=self.provider_name,
        )

    async def batch_geocode(
        self,
        addresses: list[str],
        http_client: httpx.AsyncClient | None = None,
    ) -> list[GeocodingResult]:
        """Geocode a list of addresses serially using single geocode() calls.

        Nominatim does not provide a native batch endpoint; calls are made
        one at a time and results are returned in input order.

        Args:
            addresses: List of freeform address strings.
            http_client: Optional override client shared across all calls.

        Returns:
            List of GeocodingResult in the same order as input.
        """
        results = []
        for addr in addresses:
            result = await self.geocode(addr, http_client=http_client)
            results.append(result)
        return results


async def _nominatim_reachable(
    base_url: str,
    http_client: httpx.AsyncClient,
    timeout_s: float = 2.0,
) -> bool:
    """HTTP probe — GET {base_url}/status with 2s timeout.

    Returns True on HTTP 200, False on any error (network, timeout, non-200).
    Used by main.py lifespan to conditionally register the Nominatim provider.
    """
    url = f"{base_url.rstrip('/')}/status"
    try:
        response = await http_client.get(url, timeout=timeout_s)
        return response.status_code == 200
    except Exception:
        return False
