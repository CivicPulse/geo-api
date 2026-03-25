"""add oa parcels table

Revision ID: d4a71c3f8b92
Revises: c1f84b2e9a07
Create Date: 2026-03-25 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from geoalchemy2 import Geography

# revision identifiers, used by Alembic.
revision: str = 'd4a71c3f8b92'
down_revision: Union[str, Sequence[str], None] = 'c1f84b2e9a07'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema — create openaddresses_parcels staging table."""
    op.create_geospatial_table('openaddresses_parcels',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('source_hash', sa.String(length=64), nullable=False),
    sa.Column('pid', sa.String(length=50), nullable=True),
    sa.Column('county', sa.String(length=100), nullable=True),
    sa.Column('state', sa.String(length=10), nullable=True),
    sa.Column('boundary', Geography(
        geometry_type='POLYGON', srid=4326, dimension=2,
        spatial_index=False, from_text='ST_GeogFromText', name='geography',
    ), nullable=True),
    sa.Column('address_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.ForeignKeyConstraint(['address_id'], ['addresses.id'], name='fk_oa_parcels_address_id'),
    sa.UniqueConstraint('source_hash', name='uq_oa_parcel_source_hash'),
    )
    op.create_geospatial_index(
        'idx_oa_parcels_boundary', 'openaddresses_parcels', ['boundary'],
        unique=False, postgresql_using='gist', postgresql_ops={},
    )
    op.create_index('idx_oa_parcels_pid', 'openaddresses_parcels', ['pid'])
    op.create_index('idx_oa_parcels_state_county', 'openaddresses_parcels', ['state', 'county'])
    op.create_index('idx_oa_parcels_address_id', 'openaddresses_parcels', ['address_id'])


def downgrade() -> None:
    """Downgrade schema — drop openaddresses_parcels staging table."""
    op.drop_index('idx_oa_parcels_address_id', table_name='openaddresses_parcels')
    op.drop_index('idx_oa_parcels_state_county', table_name='openaddresses_parcels')
    op.drop_index('idx_oa_parcels_pid', table_name='openaddresses_parcels')
    op.drop_geospatial_index('idx_oa_parcels_boundary', table_name='openaddresses_parcels', postgresql_using='gist', column_name='boundary')
    op.drop_geospatial_table('openaddresses_parcels')
