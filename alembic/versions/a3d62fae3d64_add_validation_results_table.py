"""add validation_results table

Revision ID: a3d62fae3d64
Revises: b98c26825b02
Create Date: 2026-03-19 14:18:26.692053

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a3d62fae3d64'
down_revision: Union[str, Sequence[str], None] = 'b98c26825b02'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema — create validation_results table."""
    op.create_table('validation_results',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('address_id', sa.Integer(), nullable=False),
    sa.Column('provider_name', sa.String(length=50), nullable=False),
    sa.Column('normalized_address', sa.Text(), nullable=True),
    sa.Column('address_line_1', sa.Text(), nullable=True),
    sa.Column('address_line_2', sa.Text(), nullable=True),
    sa.Column('city', sa.String(length=100), nullable=True),
    sa.Column('state', sa.String(length=2), nullable=True),
    sa.Column('postal_code', sa.String(length=10), nullable=True),
    sa.Column('confidence', sa.Float(), nullable=True),
    sa.Column('delivery_point_verified', sa.Boolean(), nullable=False),
    sa.Column('raw_response', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['address_id'], ['addresses.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('address_id', 'provider_name', name='uq_validation_address_provider')
    )
    op.create_index(op.f('ix_validation_results_address_id'), 'validation_results', ['address_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema — drop validation_results table."""
    op.drop_index(op.f('ix_validation_results_address_id'), table_name='validation_results')
    op.drop_table('validation_results')
