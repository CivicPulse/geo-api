from __future__ import annotations

from typing import TYPE_CHECKING

from geoalchemy2.types import Geography
from sqlalchemy import Enum as PgEnum
from sqlalchemy import Float, ForeignKey, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from civpulse_geo.models.base import Base, TimestampMixin
from civpulse_geo.models.enums import LocationType

if TYPE_CHECKING:
    from civpulse_geo.models.address import Address


class GeocodingResult(Base, TimestampMixin):
    __tablename__ = "geocoding_results"
    __table_args__ = (
        UniqueConstraint(
            "address_id", "provider_name", name="uq_geocoding_address_provider"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    address_id: Mapped[int] = mapped_column(
        ForeignKey("addresses.id"), nullable=False, index=True
    )
    provider_name: Mapped[str] = mapped_column(String(50), nullable=False)

    # PostGIS geography column — distance-in-meters semantics
    location: Mapped[object] = mapped_column(
        Geography(geometry_type="POINT", srid=4326), nullable=True
    )

    # Denormalized lat/lng for easy JSON serialization without WKB parsing
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)

    location_type: Mapped[LocationType | None] = mapped_column(
        PgEnum(LocationType, name="locationtype", create_type=True), nullable=True
    )
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    raw_response: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Relationships
    address: Mapped[Address] = relationship("Address", back_populates="geocoding_results")


class OfficialGeocoding(Base, TimestampMixin):
    __tablename__ = "official_geocoding"

    id: Mapped[int] = mapped_column(primary_key=True)
    address_id: Mapped[int] = mapped_column(
        ForeignKey("addresses.id"), nullable=False, unique=True
    )
    geocoding_result_id: Mapped[int] = mapped_column(
        ForeignKey("geocoding_results.id"), nullable=False
    )
    set_by_stage: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    address: Mapped[Address] = relationship("Address")
    geocoding_result: Mapped[GeocodingResult] = relationship("GeocodingResult")


class AdminOverride(Base, TimestampMixin):
    __tablename__ = "admin_overrides"

    id: Mapped[int] = mapped_column(primary_key=True)
    address_id: Mapped[int] = mapped_column(
        ForeignKey("addresses.id"), nullable=False, unique=True
    )

    # PostGIS geography column — required, not nullable (admin sets explicitly)
    location: Mapped[object] = mapped_column(
        Geography(geometry_type="POINT", srid=4326), nullable=False
    )

    # Denormalized for easy JSON serialization
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)

    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    address: Mapped[Address] = relationship("Address")
