"""ORM model for OpenAddresses parcel boundary staging table."""
from geoalchemy2.types import Geography
from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from civpulse_geo.models.base import Base, TimestampMixin


class OpenAddressesParcel(Base, TimestampMixin):
    """Staging table for OpenAddresses parcel boundary data.

    Source data is .geojson.gz files with hash, pid, and Polygon geometry.
    The source_hash uniquely identifies each source record for upsert support.
    county and state are populated from CLI flags, not GeoJSON properties.
    address_id is left NULL at import and populated later via spatial join.
    """

    __tablename__ = "openaddresses_parcels"
    __table_args__ = (
        UniqueConstraint("source_hash", name="uq_oa_parcel_source_hash"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    pid: Mapped[str | None] = mapped_column(String(50))
    county: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str | None] = mapped_column(String(10))
    boundary: Mapped[object] = mapped_column(
        Geography(geometry_type="POLYGON", srid=4326), nullable=True
    )
    address_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("addresses.id"), nullable=True
    )
