"""FastAPI router for geocoding endpoints.

Endpoints:
- POST /geocode — geocode a freeform address (cache-first)
- POST /geocode/batch — batch geocode multiple addresses concurrently (INFRA-03)
- PUT /geocode/{address_hash}/official — admin: set official result (GEO-06/07)
- POST /geocode/{address_hash}/refresh — admin: force re-query all providers (GEO-08)
- GET /geocode/{address_hash}/providers/{provider_name} — fetch provider-specific result (GEO-09)
"""
import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from civpulse_geo.config import settings
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
from civpulse_geo.schemas.batch import (
    BatchGeocodeRequest,
    BatchGeocodeResponse,
    BatchGeocodeResultItem,
    BatchItemError,
    classify_exception,
)
from civpulse_geo.services.geocoding import GeocodingService

router = APIRouter(prefix="/geocode", tags=["geocoding"])


@router.post("", response_model=GeocodeResponse)
async def geocode(
    body: GeocodeRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    dry_run: bool = Query(False, description="Run cascade without writing OfficialGeocoding"),
    trace: bool = Query(False, description="Include cascade_trace in response"),
):
    """Geocode a freeform US address.

    Returns cached results if available, otherwise calls providers and stores
    the result. The cache_hit flag indicates whether the result came from the
    database cache or a fresh provider call.

    When CASCADE_ENABLED=true:
    - dry_run=true: runs cascade without writing OfficialGeocoding; returns would_set_official
    - trace=true: includes per-stage cascade_trace in response
    """
    service = GeocodingService()
    result = await service.geocode(
        freeform=body.address,
        db=db,
        providers=request.app.state.providers,
        http_client=request.app.state.http_client,
        spell_corrector=getattr(request.app.state, "spell_corrector", None),
        fuzzy_matcher=getattr(request.app.state, "fuzzy_matcher", None),
        llm_corrector=getattr(request.app.state, "llm_corrector", None),
        dry_run=dry_run,
        trace=trace,
    )

    # Build outlier set from cascade result (empty set for legacy path)
    outlier_providers = result.get("outlier_providers", set())

    # Transform ORM results to Pydantic response models
    provider_results = [
        GeocodeProviderResult(
            provider_name=r.provider_name,
            latitude=r.latitude,
            longitude=r.longitude,
            location_type=r.location_type.value if r.location_type else None,
            confidence=r.confidence,
            is_outlier=r.provider_name in outlier_providers,
        )
        for r in result["results"]
    ]

    # Local provider results (dataclass schema — lat/lng field names differ from ORM)
    local_provider_results = [
        GeocodeProviderResult(
            provider_name=r.provider_name,
            latitude=r.lat,
            longitude=r.lng,
            location_type=r.location_type,
            confidence=r.confidence,
            is_outlier=r.provider_name in outlier_providers,
        )
        for r in result.get("local_results", [])
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

    # Build would_set_official from CascadeResult (for dry_run mode)
    would_set = None
    ws = result.get("would_set_official")
    if ws is not None:
        # ws is a ProviderCandidate dataclass from cascade.py
        would_set = GeocodeProviderResult(
            provider_name=ws.provider_name,
            latitude=ws.lat,
            longitude=ws.lng,
            location_type=ws.location_type,
            confidence=ws.confidence,
        )

    return GeocodeResponse(
        address_hash=result["address_hash"],
        normalized_address=result["normalized_address"],
        cache_hit=result["cache_hit"],
        results=provider_results,
        local_results=local_provider_results,
        official=official,
        cascade_trace=result.get("cascade_trace"),
        would_set_official=would_set,
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


# ---------------------------------------------------------------------------
# Batch geocoding (INFRA-03)
# ---------------------------------------------------------------------------


async def _geocode_one(
    index: int,
    freeform: str,
    semaphore: asyncio.Semaphore,
    service: GeocodingService,
    db: AsyncSession,
    providers: dict,
    http_client,
    spell_corrector=None,
    fuzzy_matcher=None,
    llm_corrector=None,
) -> BatchGeocodeResultItem:
    """Process a single address within a batch. Catches all exceptions per-item."""
    try:
        async with semaphore:
            result = await service.geocode(
                freeform=freeform,
                db=db,
                providers=providers,
                http_client=http_client,
                spell_corrector=spell_corrector,
                fuzzy_matcher=fuzzy_matcher,
                llm_corrector=llm_corrector,
            )

        # Build outlier set from cascade result (empty set for legacy path)
        outlier_providers = result.get("outlier_providers", set())

        # Transform ORM results to Pydantic (same pattern as single geocode endpoint)
        provider_results = [
            GeocodeProviderResult(
                provider_name=r.provider_name,
                latitude=r.latitude,
                longitude=r.longitude,
                location_type=r.location_type.value if r.location_type else None,
                confidence=r.confidence,
                is_outlier=r.provider_name in outlier_providers,
            )
            for r in result["results"]
        ]
        local_provider_results = [
            GeocodeProviderResult(
                provider_name=r.provider_name,
                latitude=r.lat,
                longitude=r.lng,
                location_type=r.location_type,
                confidence=r.confidence,
                is_outlier=r.provider_name in outlier_providers,
            )
            for r in result.get("local_results", [])
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
        data = GeocodeResponse(
            address_hash=result["address_hash"],
            normalized_address=result["normalized_address"],
            cache_hit=result["cache_hit"],
            results=provider_results,
            local_results=local_provider_results,
            official=official,
            cascade_trace=None,
            would_set_official=None,
        )
        return BatchGeocodeResultItem(
            index=index,
            original_input=freeform,
            status_code=200,
            status="success",
            data=data,
            error=None,
        )
    except Exception as exc:
        status_code, status, message = classify_exception(exc)
        return BatchGeocodeResultItem(
            index=index,
            original_input=freeform,
            status_code=status_code,
            status=status,
            data=None,
            error=BatchItemError(message=message),
        )


@router.post("/batch", response_model=BatchGeocodeResponse)
async def batch_geocode(
    body: BatchGeocodeRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Batch geocode multiple addresses concurrently.

    Returns per-item results with individual status codes. One item failing
    does not affect other items. Returns outer 422 only when ALL items fail.
    Note: batch does not support dry_run or trace (single-address debugging features).
    """
    if not body.addresses:
        return BatchGeocodeResponse(total=0, succeeded=0, failed=0, results=[])

    semaphore = asyncio.Semaphore(settings.batch_concurrency_limit)
    service = GeocodingService()
    spell_corrector = getattr(request.app.state, "spell_corrector", None)
    fuzzy_matcher = getattr(request.app.state, "fuzzy_matcher", None)
    llm_corrector = getattr(request.app.state, "llm_corrector", None)

    items = await asyncio.gather(*[
        _geocode_one(
            index=i,
            freeform=addr,
            semaphore=semaphore,
            service=service,
            db=db,
            providers=request.app.state.providers,
            http_client=request.app.state.http_client,
            spell_corrector=spell_corrector,
            fuzzy_matcher=fuzzy_matcher,
            llm_corrector=llm_corrector,
        )
        for i, addr in enumerate(body.addresses)
    ])

    succeeded = sum(1 for item in items if item.status_code == 200)
    failed = len(items) - succeeded
    response_body = BatchGeocodeResponse(
        total=len(items),
        succeeded=succeeded,
        failed=failed,
        results=list(items),
    )

    if succeeded == 0 and failed > 0:
        return JSONResponse(status_code=422, content=response_body.model_dump())
    return response_body
