"""ORM model for OpenAddresses staging table."""
from geoalchemy2.types import Geography
from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from civpulse_geo.models.base import Base, TimestampMixin


class OpenAddressesPoint(Base, TimestampMixin):
    """Staging table for OpenAddresses address point data.

    Source data is .geojson.gz files from openaddresses.io.
    The source_hash uniquely identifies each source record for upsert support.
    Phase 8 implements the data loading logic that populates this table.
    """

    __tablename__ = "openaddresses_points"
    __table_args__ = (
        UniqueConstraint("source_hash", name="uq_oa_source_hash"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    street_number: Mapped[str | None] = mapped_column(String(20))
    street_name: Mapped[str | None] = mapped_column(String(200))
    street_suffix: Mapped[str | None] = mapped_column(String(20))
    unit: Mapped[str | None] = mapped_column(String(50))
    city: Mapped[str | None] = mapped_column(String(100))
    district: Mapped[str | None] = mapped_column(String(100))
    region: Mapped[str | None] = mapped_column(String(100))  # OA "region" = state
    postcode: Mapped[str | None] = mapped_column(String(20))
    location: Mapped[object] = mapped_column(
        Geography(geometry_type="POINT", srid=4326), nullable=True
    )
    accuracy: Mapped[str | None] = mapped_column(String(50))  # OA accuracy field
