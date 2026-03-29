"""Add set_by_stage column to official_geocoding table.

Revision ID: h8e5f1g4a7b3
Revises: g7d4e0f3a6b2
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "h8e5f1g4a7b3"
down_revision: Union[str, Sequence[str], None] = "g7d4e0f3a6b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "official_geocoding",
        sa.Column("set_by_stage", sa.Text, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("official_geocoding", "set_by_stage")
