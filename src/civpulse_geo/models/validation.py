"""ORM model for address validation results.

Defines ValidationResult, the SQLAlchemy model for the validation_results table.
Mirrors the GeocodingResult pattern from models/geocoding.py.

Each row represents one provider's normalization of one address.
The unique constraint uq_validation_address_provider enforces one result per
(address, provider) pair — matching the geocoding_results convention.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Float, ForeignKey, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from civpulse_geo.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from civpulse_geo.models.address import Address


class ValidationResult(Base, TimestampMixin):
    """ORM model for address validation results.

    Stores the output of a validation provider (e.g. scourgify) for a given address.
    address_id links to the canonical address record in the addresses table.

    Columns:
        id: Primary key.
        address_id: FK to addresses.id — the address that was validated.
        provider_name: String identifier for the provider (e.g. "scourgify").
        normalized_address: Full USPS-normalized address string.
        address_line_1: Normalized street line.
        address_line_2: Secondary designator (APT, STE, etc.) or NULL.
        city: City name.
        state: Two-letter state abbreviation.
        postal_code: ZIP5 or ZIP+4 (String(10) to accommodate ZIP+4).
        confidence: Provider confidence score (1.0 for scourgify success).
        delivery_point_verified: True only for providers with USPS DPV; False for scourgify.
        raw_response: Full provider response dict for audit/debugging.
    """
    __tablename__ = "validation_results"
    __table_args__ = (
        UniqueConstraint(
            "address_id", "provider_name", name="uq_validation_address_provider"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    address_id: Mapped[int] = mapped_column(
        ForeignKey("addresses.id"), nullable=False, index=True
    )
    provider_name: Mapped[str] = mapped_column(String(50), nullable=False)

    normalized_address: Mapped[str | None] = mapped_column(Text)
    address_line_1: Mapped[str | None] = mapped_column(Text)
    address_line_2: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str | None] = mapped_column(String(2))
    postal_code: Mapped[str | None] = mapped_column(String(10))  # ZIP+4 support
    confidence: Mapped[float | None] = mapped_column(Float)
    delivery_point_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    raw_response: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Relationship
    address: Mapped["Address"] = relationship("Address")
