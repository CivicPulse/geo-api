"""FastAPI router for the POST /geocode endpoint.

Wires together the HTTP layer with GeocodingService. The router:
- Validates the request body with GeocodeRequest
- Injects the database session via get_db dependency
- Reads the shared http_client and providers from app.state
- Delegates all logic to GeocodingService
- Transforms ORM results into GeocodeResponse Pydantic model
"""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from civpulse_geo.database import get_db
from civpulse_geo.schemas.geocoding import (
    GeocodeRequest,
    GeocodeResponse,
    GeocodeProviderResult,
)
from civpulse_geo.services.geocoding import GeocodingService

router = APIRouter(prefix="/geocode", tags=["geocoding"])


@router.post("", response_model=GeocodeResponse)
async def geocode(
    body: GeocodeRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Geocode a freeform US address.

    Returns cached results if available, otherwise calls the Census Geocoder
    and stores the result. The cache_hit flag indicates whether the result
    came from the database cache or a fresh provider call.
    """
    service = GeocodingService()
    result = await service.geocode(
        freeform=body.address,
        db=db,
        providers=request.app.state.providers,
        http_client=request.app.state.http_client,
    )

    # Transform ORM results to Pydantic response models
    provider_results = [
        GeocodeProviderResult(
            provider_name=r.provider_name,
            latitude=r.latitude,
            longitude=r.longitude,
            location_type=r.location_type.value if r.location_type else None,
            confidence=r.confidence,
        )
        for r in result["results"]
    ]

    official = None
    if result.get("official"):
        o = result["official"]
        official = GeocodeProviderResult(
            provider_name=o.provider_name,
            latitude=o.latitude,
            longitude=o.longitude,
            location_type=o.location_type.value if o.location_type else None,
            confidence=o.confidence,
        )

    return GeocodeResponse(
        address_hash=result["address_hash"],
        normalized_address=result["normalized_address"],
        cache_hit=result["cache_hit"],
        results=provider_results,
        official=official,
    )
