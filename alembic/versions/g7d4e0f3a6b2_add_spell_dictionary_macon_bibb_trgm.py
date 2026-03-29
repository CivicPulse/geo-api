"""Add spell_dictionary table and Macon-Bibb GIN trigram index.

Revision ID: g7d4e0f3a6b2
Revises: f6c3d9e2b5a1
Create Date: 2026-03-29
"""
import sqlalchemy as sa
from alembic import op

revision = "g7d4e0f3a6b2"
down_revision = "f6c3d9e2b5a1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "spell_dictionary",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("word", sa.String(200), nullable=False, unique=True),
        sa.Column("frequency", sa.Integer, nullable=False, server_default="1"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index("idx_spell_dictionary_word", "spell_dictionary", ["word"])
    op.execute(
        "CREATE INDEX idx_macon_bibb_street_trgm "
        "ON macon_bibb_points USING gin (street_name gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_macon_bibb_street_trgm")
    op.drop_index("idx_spell_dictionary_word")
    op.drop_table("spell_dictionary")
