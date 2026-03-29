"""Add pg_trgm extension and GIN trigram indexes on street_name columns.

Revision ID: f6c3d9e2b5a1
Revises: e5b2a1d3f4c6
Create Date: 2026-03-29
"""
from alembic import op

revision = "f6c3d9e2b5a1"
down_revision = "e5b2a1d3f4c6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        "CREATE INDEX idx_oa_points_street_trgm "
        "ON openaddresses_points USING gin (street_name gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX idx_nad_points_street_name_trgm "
        "ON nad_points USING gin (street_name gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_nad_points_street_name_trgm")
    op.execute("DROP INDEX IF EXISTS idx_oa_points_street_trgm")
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
