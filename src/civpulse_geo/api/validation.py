"""FastAPI router for address validation endpoints.

Endpoints:
- POST /validate -- validate and USPS-standardize an address (cache-first)
- POST /validate/batch -- batch validate multiple addresses concurrently (INFRA-04/INFRA-06)
"""
import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from civpulse_geo.config import settings
from civpulse_geo.database import get_db
from civpulse_geo.schemas.validation import (
    ValidateRequest,
    ValidateResponse,
    ValidationCandidate,
)
from civpulse_geo.schemas.batch import (
    BatchValidateRequest,
    BatchValidateResponse,
    BatchValidateResultItem,
    BatchItemError,
    classify_exception,
)
from civpulse_geo.services.validation import ValidationService
from civpulse_geo.providers.exceptions import ProviderError

router = APIRouter(prefix="/validate", tags=["validation"])


@router.post("", response_model=ValidateResponse)
async def validate_address(
    body: ValidateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Validate and USPS-standardize a US address.

    Accepts either a freeform address string OR structured fields (street, city, state, zip_code).
    Returns USPS-normalized candidates with confidence scores.
    Returns 422 if the address is unparseable by scourgify.

    The cache_hit flag indicates whether the result came from the database cache
    or a fresh provider call.
    """
    service = ValidationService()
    freeform = body.to_freeform()

    try:
        result = await service.validate(
            freeform=freeform,
            db=db,
            providers=request.app.state.validation_providers,
        )
    except ProviderError as e:
        raise HTTPException(status_code=422, detail=str(e))

    candidates = [
        ValidationCandidate(
            normalized_address=c.normalized_address or "",
            address_line_1=c.address_line_1,
            address_line_2=c.address_line_2,
            city=c.city,
            state=c.state,
            postal_code=c.postal_code,
            confidence=c.confidence or 0.0,
            delivery_point_verified=c.delivery_point_verified,
            provider_name=c.provider_name,
        )
        for c in result["candidates"]
    ]

    return ValidateResponse(
        address_hash=result["address_hash"],
        original_input=freeform,
        candidates=candidates,
        cache_hit=result["cache_hit"],
    )


# ---------------------------------------------------------------------------
# Batch validation (INFRA-04 / INFRA-06)
# ---------------------------------------------------------------------------


async def _validate_one(
    index: int,
    freeform: str,
    semaphore: asyncio.Semaphore,
    service: ValidationService,
    db: AsyncSession,
    providers: dict,
) -> BatchValidateResultItem:
    """Process a single validation within a batch. Catches all exceptions per-item."""
    try:
        async with semaphore:
            result = await service.validate(
                freeform=freeform, db=db, providers=providers
            )
        # Transform ORM results to Pydantic (same pattern as single validate endpoint)
        candidates = [
            ValidationCandidate(
                normalized_address=c.normalized_address or "",
                address_line_1=c.address_line_1,
                address_line_2=c.address_line_2,
                city=c.city,
                state=c.state,
                postal_code=c.postal_code,
                confidence=c.confidence or 0.0,
                delivery_point_verified=c.delivery_point_verified,
                provider_name=c.provider_name,
            )
            for c in result["candidates"]
        ]
        data = ValidateResponse(
            address_hash=result["address_hash"],
            original_input=result["original_input"],
            candidates=candidates,
            cache_hit=result["cache_hit"],
        )
        return BatchValidateResultItem(
            index=index,
            original_input=freeform,
            status_code=200,
            status="success",
            data=data,
            error=None,
        )
    except Exception as exc:
        status_code, status, message = classify_exception(exc)
        return BatchValidateResultItem(
            index=index,
            original_input=freeform,
            status_code=status_code,
            status=status,
            data=None,
            error=BatchItemError(message=message),
        )


@router.post("/batch", response_model=BatchValidateResponse)
async def batch_validate(
    body: BatchValidateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Batch validate multiple addresses concurrently.

    Returns per-item results with individual status codes. One item failing
    does not affect other items. Returns outer 422 only when ALL items fail.
    """
    if not body.addresses:
        return BatchValidateResponse(total=0, succeeded=0, failed=0, results=[])

    semaphore = asyncio.Semaphore(settings.batch_concurrency_limit)
    service = ValidationService()

    items = await asyncio.gather(*[
        _validate_one(
            index=i,
            freeform=addr,
            semaphore=semaphore,
            service=service,
            db=db,
            providers=request.app.state.validation_providers,
        )
        for i, addr in enumerate(body.addresses)
    ])

    succeeded = sum(1 for item in items if item.status_code == 200)
    failed = len(items) - succeeded
    response_body = BatchValidateResponse(
        total=len(items),
        succeeded=succeeded,
        failed=failed,
        results=list(items),
    )

    if succeeded == 0 and failed > 0:
        return JSONResponse(status_code=422, content=response_body.model_dump())
    return response_body
