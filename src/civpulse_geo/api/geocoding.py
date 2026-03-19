"""FastAPI router for geocoding endpoints.

Endpoints:
- POST /geocode — geocode a freeform address (cache-first)
- PUT /geocode/{address_hash}/official — admin: set official result (GEO-06/07)
- POST /geocode/{address_hash}/refresh — admin: force re-query all providers (GEO-08)
- GET /geocode/{address_hash}/providers/{provider_name} — fetch provider-specific result (GEO-09)
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from civpulse_geo.database import get_db
from civpulse_geo.schemas.geocoding import (
    GeocodeRequest,
    GeocodeResponse,
    GeocodeProviderResult,
    SetOfficialRequest,
    OfficialResponse,
    RefreshResponse,
    ProviderResultResponse,
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


@router.put("/{address_hash}/official", response_model=OfficialResponse)
async def set_official(
    address_hash: str,
    body: SetOfficialRequest,
    db: AsyncSession = Depends(get_db),
):
    """Set the official geocoding result for an address (GEO-06/07).

    Pass geocoding_result_id to point at an existing provider result, or pass
    latitude+longitude to create a custom admin_override coordinate.
    Returns 404 if the address_hash or geocoding_result_id is not found.
    """
    service = GeocodingService()
    try:
        result = await service.set_official(
            address_hash=address_hash,
            db=db,
            geocoding_result_id=body.geocoding_result_id,
            latitude=body.latitude,
            longitude=body.longitude,
            reason=body.reason,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    official = result["official"]
    return OfficialResponse(
        address_hash=address_hash,
        official=GeocodeProviderResult(
            provider_name=official.provider_name,
            latitude=official.latitude,
            longitude=official.longitude,
            location_type=official.location_type.value if official.location_type else None,
            confidence=official.confidence,
        ),
        source=result["source"],
    )


@router.post("/{address_hash}/refresh", response_model=RefreshResponse)
async def refresh_geocode(
    address_hash: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Force re-query of all providers for an address (GEO-08).

    Bypasses the cache and calls every registered provider. Results are upserted.
    Returns 404 if the address_hash is not found.
    """
    service = GeocodingService()
    try:
        result = await service.refresh(
            address_hash=address_hash,
            db=db,
            providers=request.app.state.providers,
            http_client=request.app.state.http_client,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return RefreshResponse(
        address_hash=result["address_hash"],
        normalized_address=result["normalized_address"],
        results=[
            GeocodeProviderResult(
                provider_name=r.provider_name,
                latitude=r.latitude,
                longitude=r.longitude,
                location_type=r.location_type.value if r.location_type else None,
                confidence=r.confidence,
            )
            for r in result["results"]
        ],
        refreshed_providers=result["refreshed_providers"],
    )


@router.get("/{address_hash}/providers/{provider_name}", response_model=ProviderResultResponse)
async def get_provider_result(
    address_hash: str,
    provider_name: str,
    db: AsyncSession = Depends(get_db),
):
    """Fetch the result from a specific provider for an address (GEO-09).

    Returns 404 if the address_hash or provider_name is not found.
    """
    service = GeocodingService()
    try:
        result = await service.get_by_provider(
            address_hash=address_hash,
            provider_name=provider_name,
            db=db,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    r = result["result"]
    return ProviderResultResponse(
        address_hash=address_hash,
        provider_name=r.provider_name,
        latitude=r.latitude,
        longitude=r.longitude,
        location_type=r.location_type.value if r.location_type else None,
        confidence=r.confidence,
        raw_response=r.raw_response,
    )
