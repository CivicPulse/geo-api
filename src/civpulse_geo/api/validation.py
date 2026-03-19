"""FastAPI router for address validation endpoints.

Endpoints:
- POST /validate -- validate and USPS-standardize an address (cache-first)
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from civpulse_geo.database import get_db
from civpulse_geo.schemas.validation import (
    ValidateRequest,
    ValidateResponse,
    ValidationCandidate,
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
