"""ORM model for the spell correction dictionary table."""
from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from civpulse_geo.models.base import Base


class SpellDictionary(Base):
    """Centralized spell correction dictionary populated from staging tables.

    Each row represents one word token extracted from street names in the
    openaddresses_points, nad_points, and macon_bibb_points staging tables.
    The dictionary is rebuilt automatically after each CLI data load command
    and loaded into memory at API worker startup (D-08, D-09).
    """

    __tablename__ = "spell_dictionary"

    id: Mapped[int] = mapped_column(primary_key=True)
    word: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    frequency: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
