from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from civpulse_geo.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from civpulse_geo.models.geocoding import GeocodingResult


class Address(Base, TimestampMixin):
    __tablename__ = "addresses"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Raw input as received from caller
    original_input: Mapped[str] = mapped_column(Text, nullable=False)

    # USPS-standardized canonical form
    normalized_address: Mapped[str] = mapped_column(Text, nullable=False)

    # SHA-256 hex of normalized_address for fast cache lookups
    address_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )

    # Parsed address components — all nullable
    street_number: Mapped[str | None] = mapped_column(String(20))
    street_name: Mapped[str | None] = mapped_column(String(200))
    street_suffix: Mapped[str | None] = mapped_column(String(20))
    street_predirection: Mapped[str | None] = mapped_column(String(5))
    street_postdirection: Mapped[str | None] = mapped_column(String(5))
    unit_type: Mapped[str | None] = mapped_column(String(20))
    unit_number: Mapped[str | None] = mapped_column(String(20))
    city: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str | None] = mapped_column(String(2))
    zip_code: Mapped[str | None] = mapped_column(String(5))  # ZIP5 only

    # Self-referencing FK: unit records point to their base address (no unit)
    base_address_id: Mapped[int | None] = mapped_column(
        ForeignKey("addresses.id"), nullable=True
    )

    # Relationships
    geocoding_results: Mapped[list[GeocodingResult]] = relationship(
        "GeocodingResult", back_populates="address", cascade="all, delete-orphan"
    )
    base_address: Mapped[Address | None] = relationship(
        "Address", remote_side="Address.id", back_populates="unit_addresses"
    )
    unit_addresses: Mapped[list[Address]] = relationship(
        "Address", back_populates="base_address"
    )
