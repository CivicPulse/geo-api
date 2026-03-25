"""ORM model for Macon-Bibb County GIS address points staging table."""
from geoalchemy2.types import Geography
from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from civpulse_geo.models.base import Base, TimestampMixin


class MaconBibbPoint(Base, TimestampMixin):
    """Staging table for Macon-Bibb County GIS Address Points data.

    Source data is GeoJSON from Macon-Bibb County GIS (data/Address_Points.geojson).
    The source_hash uniquely identifies each source record for upsert support.
    Computed as SHA-256 of "{OBJECTID}:{FULLADDR}:{lon}:{lat}".
    State is hardcoded to "GA" since this is Macon-Bibb County, Georgia.
    """

    __tablename__ = "macon_bibb_points"
    __table_args__ = (
        UniqueConstraint("source_hash", name="uq_macon_bibb_source_hash"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    street_number: Mapped[str | None] = mapped_column(String(20))   # from ADDR_HN
    street_name: Mapped[str | None] = mapped_column(String(200))    # from ADDR_SN
    street_suffix: Mapped[str | None] = mapped_column(String(20))   # from ADDR_ST
    unit: Mapped[str | None] = mapped_column(String(50))            # from UNIT
    city: Mapped[str | None] = mapped_column(String(100))           # from City_1
    state: Mapped[str | None] = mapped_column(String(10))           # hardcoded "GA"
    zip_code: Mapped[str | None] = mapped_column(String(20))        # from ZIP_1
    location: Mapped[object] = mapped_column(
        Geography(geometry_type="POINT", srid=4326), nullable=True
    )
    address_type: Mapped[str | None] = mapped_column(String(50))    # from ADDType
