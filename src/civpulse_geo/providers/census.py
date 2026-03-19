"""Census Geocoder provider adapter.

Implements GeocodingProvider using the US Census Bureau's free geocoding API:
https://geocoding.geo.census.gov/geocoder/locations/onelineaddress

Key facts about the Census API:
- No API key required
- Uses range interpolation (not rooftop accuracy)
- Confidence is fixed at 0.8 for matches (provider-specific constant)
- x = longitude, y = latitude in the response (WGS84)
- On no match: returns empty addressMatches list
"""
import httpx

from civpulse_geo.providers.base import GeocodingProvider
from civpulse_geo.providers.exceptions import ProviderNetworkError
from civpulse_geo.providers.schemas import GeocodingResult

CENSUS_GEOCODER_URL = (
    "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
)
CENSUS_CONFIDENCE = 0.8
CENSUS_NO_MATCH_CONFIDENCE = 0.0
CENSUS_LOCATION_TYPE = "RANGE_INTERPOLATED"
CENSUS_NO_MATCH_LOCATION_TYPE = "NO_MATCH"


class CensusGeocodingProvider(GeocodingProvider):
    """Geocoding provider backed by the US Census Bureau geocoder.

    The Census API is free, requires no API key, and returns WGS84 coordinates
    via range interpolation. Confidence is fixed: 0.8 for match, 0.0 for no-match.

    Args:
        http_client: Optional pre-configured httpx.AsyncClient for testing.
            If not provided, a new client is created per request.
    """

    def __init__(self, http_client: httpx.AsyncClient | None = None) -> None:
        self._client = http_client

    @property
    def provider_name(self) -> str:
        return "census"

    async def geocode(
        self,
        address: str,
        *,
        http_client: httpx.AsyncClient | None = None,
    ) -> GeocodingResult:
        """Geocode a single freeform address using the Census Geocoder API.

        Args:
            address: Freeform address string (USPS-normalized recommended).
            http_client: Optional override client for this call (e.g., in tests).

        Returns:
            GeocodingResult with lat/lng, location_type, confidence, and raw_response.

        Raises:
            ProviderNetworkError: Census API is unreachable or returned an HTTP error.
        """
        client = http_client or self._client
        params = {
            "address": address,
            "benchmark": "Public_AR_Current",
            "format": "json",
        }

        try:
            if client is not None:
                response = await client.get(CENSUS_GEOCODER_URL, params=params)
            else:
                async with httpx.AsyncClient() as auto_client:
                    response = await auto_client.get(
                        CENSUS_GEOCODER_URL, params=params
                    )
            response.raise_for_status()
        except httpx.RequestError as exc:
            raise ProviderNetworkError(
                f"Census Geocoder unreachable: {exc}"
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise ProviderNetworkError(
                f"Census Geocoder HTTP error {exc.response.status_code}: {exc}"
            ) from exc

        raw = response.json()
        matches = raw.get("result", {}).get("addressMatches", [])

        if not matches:
            return GeocodingResult(
                lat=0.0,
                lng=0.0,
                location_type=CENSUS_NO_MATCH_LOCATION_TYPE,
                confidence=CENSUS_NO_MATCH_CONFIDENCE,
                raw_response=raw,
                provider_name=self.provider_name,
            )

        coords = matches[0]["coordinates"]
        # CRITICAL: Census API uses x=longitude, y=latitude
        lat = coords["y"]
        lng = coords["x"]

        return GeocodingResult(
            lat=lat,
            lng=lng,
            location_type=CENSUS_LOCATION_TYPE,
            confidence=CENSUS_CONFIDENCE,
            raw_response=raw,
            provider_name=self.provider_name,
        )

    async def batch_geocode(
        self,
        addresses: list[str],
        http_client: httpx.AsyncClient | None = None,
    ) -> list[GeocodingResult]:
        """Geocode a list of addresses serially using single geocode() calls.

        The Census Geocoder does have a batch endpoint, but serial fallback
        is used here for simplicity and to avoid file upload complexity.

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
