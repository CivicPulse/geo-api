"""initial schema

Revision ID: b98c26825b02
Revises:
Create Date: 2026-03-19 04:21:03.449288

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from geoalchemy2 import Geography

# revision identifiers, used by Alembic.
revision: str = 'b98c26825b02'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema — create CivPulse Geo application tables."""
    # addresses: canonical address storage with parsed components and hash
    op.create_table('addresses',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('original_input', sa.Text(), nullable=False),
    sa.Column('normalized_address', sa.Text(), nullable=False),
    sa.Column('address_hash', sa.String(length=64), nullable=False),
    sa.Column('street_number', sa.String(length=20), nullable=True),
    sa.Column('street_name', sa.String(length=200), nullable=True),
    sa.Column('street_suffix', sa.String(length=20), nullable=True),
    sa.Column('street_predirection', sa.String(length=5), nullable=True),
    sa.Column('street_postdirection', sa.String(length=5), nullable=True),
    sa.Column('unit_type', sa.String(length=20), nullable=True),
    sa.Column('unit_number', sa.String(length=20), nullable=True),
    sa.Column('city', sa.String(length=100), nullable=True),
    sa.Column('state', sa.String(length=2), nullable=True),
    sa.Column('zip_code', sa.String(length=5), nullable=True),
    sa.Column('base_address_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['base_address_id'], ['addresses.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_addresses_address_hash'), 'addresses', ['address_hash'], unique=True)

    # admin_overrides: admin-set custom coordinates (highest priority in query chain)
    op.create_geospatial_table('admin_overrides',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('address_id', sa.Integer(), nullable=False),
    sa.Column('location', Geography(geometry_type='POINT', srid=4326, dimension=2, spatial_index=False, from_text='ST_GeogFromText', name='geography', nullable=False), nullable=False),
    sa.Column('latitude', sa.Float(), nullable=False),
    sa.Column('longitude', sa.Float(), nullable=False),
    sa.Column('reason', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['address_id'], ['addresses.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('address_id')
    )
    op.create_geospatial_index('idx_admin_overrides_location', 'admin_overrides', ['location'], unique=False, postgresql_using='gist', postgresql_ops={})

    # geocoding_results: provider geocode results with geography and location type
    op.create_geospatial_table('geocoding_results',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('address_id', sa.Integer(), nullable=False),
    sa.Column('provider_name', sa.String(length=50), nullable=False),
    sa.Column('location', Geography(geometry_type='POINT', srid=4326, dimension=2, spatial_index=False, from_text='ST_GeogFromText', name='geography'), nullable=True),
    sa.Column('latitude', sa.Float(), nullable=True),
    sa.Column('longitude', sa.Float(), nullable=True),
    sa.Column('location_type', sa.Enum('ROOFTOP', 'RANGE_INTERPOLATED', 'GEOMETRIC_CENTER', 'APPROXIMATE', name='locationtype'), nullable=True),
    sa.Column('confidence', sa.Float(), nullable=True),
    sa.Column('raw_response', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['address_id'], ['addresses.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('address_id', 'provider_name', name='uq_geocoding_address_provider')
    )
    op.create_geospatial_index('idx_geocoding_results_location', 'geocoding_results', ['location'], unique=False, postgresql_using='gist', postgresql_ops={})
    op.create_index(op.f('ix_geocoding_results_address_id'), 'geocoding_results', ['address_id'], unique=False)

    # official_geocoding: links each address to its designated official geocode result
    op.create_table('official_geocoding',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('address_id', sa.Integer(), nullable=False),
    sa.Column('geocoding_result_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['address_id'], ['addresses.id'], ),
    sa.ForeignKeyConstraint(['geocoding_result_id'], ['geocoding_results.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('address_id')
    )


def downgrade() -> None:
    """Downgrade schema — drop CivPulse Geo application tables in reverse dependency order."""
    op.drop_table('official_geocoding')
    op.drop_index(op.f('ix_geocoding_results_address_id'), table_name='geocoding_results')
    op.drop_geospatial_index('idx_geocoding_results_location', table_name='geocoding_results', postgresql_using='gist', column_name='location')
    op.drop_geospatial_table('geocoding_results')
    op.drop_geospatial_index('idx_admin_overrides_location', table_name='admin_overrides', postgresql_using='gist', column_name='location')
    op.drop_geospatial_table('admin_overrides')
    op.drop_index(op.f('ix_addresses_address_hash'), table_name='addresses')
    op.drop_table('addresses')
    sa.Enum(name='locationtype').drop(op.get_bind(), checkfirst=True)
