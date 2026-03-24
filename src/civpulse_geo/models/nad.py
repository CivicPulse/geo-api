"""ORM model for National Address Database (NAD) staging table."""
from geoalchemy2.types import Geography
from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from civpulse_geo.models.base import Base, TimestampMixin


class NADPoint(Base, TimestampMixin):
    """Staging table for National Address Database (NAD) address point data.

    Source data is CSV-delimited (CSVDelimited format per schema.ini) from the NAD r21 release.
    The source_hash uniquely identifies each source record for upsert support.
    Phase 10 implements the data loading logic that populates this table.
    """

    __tablename__ = "nad_points"
    __table_args__ = (
        UniqueConstraint("source_hash", name="uq_nad_source_hash"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    street_number: Mapped[str | None] = mapped_column(String(20))
    street_name: Mapped[str | None] = mapped_column(String(200))
    street_suffix: Mapped[str | None] = mapped_column(String(20))
    unit: Mapped[str | None] = mapped_column(String(50))
    city: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str | None] = mapped_column(String(100))
    zip_code: Mapped[str | None] = mapped_column(String(20))
    location: Mapped[object] = mapped_column(
        Geography(geometry_type="POINT", srid=4326), nullable=True
    )
    placement: Mapped[str | None] = mapped_column(String(50))  # NAD Placement field
