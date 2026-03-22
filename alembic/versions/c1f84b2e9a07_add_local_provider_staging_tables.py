"""add local provider staging tables

Revision ID: c1f84b2e9a07
Revises: a3d62fae3d64
Create Date: 2026-03-22 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from geoalchemy2 import Geography

# revision identifiers, used by Alembic.
revision: str = 'c1f84b2e9a07'
down_revision: Union[str, Sequence[str], None] = 'a3d62fae3d64'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema — create openaddresses_points and nad_points staging tables."""
    # openaddresses_points: staging table for OpenAddresses .geojson.gz data
    op.create_geospatial_table('openaddresses_points',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('source_hash', sa.String(length=64), nullable=False),
    sa.Column('street_number', sa.String(length=20), nullable=True),
    sa.Column('street_name', sa.String(length=200), nullable=True),
    sa.Column('street_suffix', sa.String(length=20), nullable=True),
    sa.Column('unit', sa.String(length=50), nullable=True),
    sa.Column('city', sa.String(length=100), nullable=True),
    sa.Column('district', sa.String(length=100), nullable=True),
    sa.Column('region', sa.String(length=100), nullable=True),
    sa.Column('postcode', sa.String(length=20), nullable=True),
    sa.Column('location', Geography(
        geometry_type='POINT', srid=4326, dimension=2,
        spatial_index=False, from_text='ST_GeogFromText', name='geography',
    ), nullable=True),
    sa.Column('accuracy', sa.String(length=50), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('source_hash', name='uq_oa_source_hash'),
    )
    op.create_geospatial_index(
        'idx_oa_points_location', 'openaddresses_points', ['location'],
        unique=False, postgresql_using='gist', postgresql_ops={},
    )
    op.create_index('idx_oa_points_lookup', 'openaddresses_points', ['region', 'postcode', 'street_name'])

    # nad_points: staging table for National Address Database pipe-delimited TXT data
    op.create_geospatial_table('nad_points',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('source_hash', sa.String(length=64), nullable=False),
    sa.Column('street_number', sa.String(length=20), nullable=True),
    sa.Column('street_name', sa.String(length=200), nullable=True),
    sa.Column('street_suffix', sa.String(length=20), nullable=True),
    sa.Column('unit', sa.String(length=50), nullable=True),
    sa.Column('city', sa.String(length=100), nullable=True),
    sa.Column('state', sa.String(length=100), nullable=True),
    sa.Column('zip_code', sa.String(length=20), nullable=True),
    sa.Column('location', Geography(
        geometry_type='POINT', srid=4326, dimension=2,
        spatial_index=False, from_text='ST_GeogFromText', name='geography',
    ), nullable=True),
    sa.Column('placement', sa.String(length=50), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('source_hash', name='uq_nad_source_hash'),
    )
    op.create_geospatial_index(
        'idx_nad_points_location', 'nad_points', ['location'],
        unique=False, postgresql_using='gist', postgresql_ops={},
    )
    op.create_index('idx_nad_points_lookup', 'nad_points', ['state', 'zip_code', 'street_name'])


def downgrade() -> None:
    """Downgrade schema — drop nad_points and openaddresses_points staging tables."""
    op.drop_index('idx_nad_points_lookup', table_name='nad_points')
    op.drop_geospatial_index('idx_nad_points_location', table_name='nad_points', postgresql_using='gist', column_name='location')
    op.drop_geospatial_table('nad_points')

    op.drop_index('idx_oa_points_lookup', table_name='openaddresses_points')
    op.drop_geospatial_index('idx_oa_points_location', table_name='openaddresses_points', postgresql_using='gist', column_name='location')
    op.drop_geospatial_table('openaddresses_points')
