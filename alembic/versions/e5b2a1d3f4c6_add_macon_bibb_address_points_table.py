"""add macon bibb address points table

Revision ID: e5b2a1d3f4c6
Revises: d4a71c3f8b92
Create Date: 2026-03-25 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from geoalchemy2 import Geography

# revision identifiers, used by Alembic.
revision: str = 'e5b2a1d3f4c6'
down_revision: Union[str, Sequence[str], None] = 'd4a71c3f8b92'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema — create macon_bibb_points staging table."""
    op.create_geospatial_table('macon_bibb_points',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('source_hash', sa.String(length=64), nullable=False),
    sa.Column('street_number', sa.String(length=20), nullable=True),
    sa.Column('street_name', sa.String(length=200), nullable=True),
    sa.Column('street_suffix', sa.String(length=20), nullable=True),
    sa.Column('unit', sa.String(length=50), nullable=True),
    sa.Column('city', sa.String(length=100), nullable=True),
    sa.Column('state', sa.String(length=10), nullable=True),
    sa.Column('zip_code', sa.String(length=20), nullable=True),
    sa.Column('location', Geography(
        geometry_type='POINT', srid=4326, dimension=2,
        spatial_index=False, from_text='ST_GeogFromText', name='geography',
    ), nullable=True),
    sa.Column('address_type', sa.String(length=50), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('source_hash', name='uq_macon_bibb_source_hash'),
    )
    op.create_geospatial_index(
        'idx_macon_bibb_location', 'macon_bibb_points', ['location'],
        unique=False, postgresql_using='gist', postgresql_ops={},
    )
    op.create_index(
        'idx_macon_bibb_street_name_zip',
        'macon_bibb_points',
        ['street_name', 'zip_code'],
    )


def downgrade() -> None:
    """Downgrade schema — drop macon_bibb_points staging table."""
    op.drop_index('idx_macon_bibb_street_name_zip', table_name='macon_bibb_points')
    op.drop_geospatial_index(
        'idx_macon_bibb_location',
        table_name='macon_bibb_points',
        postgresql_using='gist',
        column_name='location',
    )
    op.drop_geospatial_table('macon_bibb_points')
