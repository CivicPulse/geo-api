"""Seed script for CivPulse Geo API.

Loads address data from Bibb County GeoJSON samples plus synthetic edge-case
addresses into the database. Designed for idempotent re-runs using
INSERT ... ON CONFLICT DO NOTHING.

Usage:
    uv run python scripts/seed.py
    uv run python scripts/seed.py --geojson data/SAMPLE_Address_Points.geojson
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import typer
from geoalchemy2 import WKTElement
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

# Allow importing from src layout without installing as editable
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from civpulse_geo.config import settings
from civpulse_geo.normalization import canonical_key, parse_address_components

app = typer.Typer(help="Seed the CivPulse Geo database with sample address data.")

# Default GeoJSON path — relative to project root
DEFAULT_GEOJSON = Path(__file__).parent.parent / "data" / "SAMPLE_Address_Points.geojson"

# Synthetic edge-case addresses to test normalization coverage
SYNTHETIC_ADDRESSES = [
    "100 Pine St Apt 4B, Macon, GA 31201",          # unit number
    "PO Box 1234, Macon, GA 31201",                  # PO Box — scourgify fallback
    "456 North Oak Avenue, Atlanta, GA 30301",        # directional + full suffix
    "789 Elm Rd, Macon, Georgia 31201-5678",          # state name + ZIP+4
    "321 Martin Luther King Jr Blvd, Macon, GA 31201", # long street name
]


def _build_wkt_point(longitude: float, latitude: float) -> WKTElement:
    """Build a WKTElement for a Geography(POINT) column."""
    return WKTElement(f"POINT({longitude} {latitude})", srid=4326)


def _insert_address(
    conn,
    original_input: str,
    normalized_address: str,
    address_hash: str,
    components: dict,
) -> int | None:
    """Insert an address row, ignoring conflicts on address_hash.

    Returns the address id (existing or newly inserted).
    """
    result = conn.execute(
        text("""
            INSERT INTO addresses (
                original_input, normalized_address, address_hash,
                street_number, street_name, street_suffix,
                street_predirection, street_postdirection,
                unit_type, unit_number,
                city, state, zip_code
            ) VALUES (
                :original_input, :normalized_address, :address_hash,
                :street_number, :street_name, :street_suffix,
                :street_predirection, :street_postdirection,
                :unit_type, :unit_number,
                :city, :state, :zip_code
            )
            ON CONFLICT (address_hash) DO NOTHING
            RETURNING id
        """),
        {
            "original_input": original_input,
            "normalized_address": normalized_address,
            "address_hash": address_hash,
            "street_number": components.get("street_number"),
            "street_name": components.get("street_name"),
            "street_suffix": components.get("street_suffix"),
            "street_predirection": components.get("street_predirection"),
            "street_postdirection": components.get("street_postdirection"),
            "unit_type": components.get("unit_type"),
            "unit_number": components.get("unit_number"),
            "city": components.get("city"),
            "state": components.get("state"),
            "zip_code": components.get("zip_code"),
        },
    )
    row = result.fetchone()
    if row:
        return row[0]

    # Address already exists — fetch existing id
    existing = conn.execute(
        text("SELECT id FROM addresses WHERE address_hash = :hash"),
        {"hash": address_hash},
    ).fetchone()
    return existing[0] if existing else None


def _insert_geocoding_result(
    conn,
    address_id: int,
    latitude: float,
    longitude: float,
    provider_name: str = "bibb_county_gis",
) -> None:
    """Insert a geocoding result, ignoring conflicts on (address_id, provider_name)."""
    wkt_point = _build_wkt_point(longitude, latitude)
    conn.execute(
        text("""
            INSERT INTO geocoding_results (
                address_id, provider_name, location, latitude, longitude
            ) VALUES (
                :address_id, :provider_name,
                ST_GeogFromText(:location),
                :latitude, :longitude
            )
            ON CONFLICT (address_id, provider_name) DO NOTHING
        """),
        {
            "address_id": address_id,
            "provider_name": provider_name,
            "location": f"SRID=4326;POINT({longitude} {latitude})",
            "latitude": latitude,
            "longitude": longitude,
        },
    )


def load_geojson_addresses(geojson_path: Path, conn) -> tuple[int, int]:
    """Load addresses from a GeoJSON file.

    Returns (addresses_inserted, geocoding_results_inserted).
    """
    typer.echo(f"Loading GeoJSON from: {geojson_path}")

    with geojson_path.open() as f:
        data = json.load(f)

    features = data.get("features", [])
    typer.echo(f"Found {len(features)} features in GeoJSON")

    addr_count = 0
    geo_count = 0

    for feature in features:
        props = feature.get("properties", {})
        geometry = feature.get("geometry", {})

        # Extract address components from GeoJSON properties
        fulladdr = (props.get("FULLADDR") or "").strip()
        city = (props.get("City_1") or "").strip()
        state = "GA"  # Bibb County, Georgia
        zip_code = (props.get("ZIP_1") or "").strip()

        if not fulladdr:
            continue

        # Build a freeform address string for normalization
        freeform = f"{fulladdr}, {city}, {state} {zip_code}".strip(", ")

        normalized, address_hash = canonical_key(freeform)
        components = parse_address_components(freeform)

        address_id = _insert_address(conn, freeform, normalized, address_hash, components)
        if address_id:
            addr_count += 1

            # Insert geocoding result if geometry is available
            coords = geometry.get("coordinates")
            if coords and len(coords) >= 2 and address_id:
                longitude, latitude = coords[0], coords[1]
                _insert_geocoding_result(conn, address_id, latitude, longitude)
                geo_count += 1

    return addr_count, geo_count


def load_synthetic_addresses(conn) -> int:
    """Load synthetic edge-case addresses (no geocoding results — no real coords).

    Returns count of addresses processed.
    """
    typer.echo(f"Loading {len(SYNTHETIC_ADDRESSES)} synthetic edge-case addresses")
    count = 0
    for freeform in SYNTHETIC_ADDRESSES:
        normalized, address_hash = canonical_key(freeform)
        components = parse_address_components(freeform)
        address_id = _insert_address(conn, freeform, normalized, address_hash, components)
        if address_id:
            count += 1
    return count


@app.command()
def main(
    geojson: Optional[Path] = typer.Option(
        None,
        "--geojson",
        help="Path to GeoJSON file with address points. Defaults to data/SAMPLE_Address_Points.geojson.",
    ),
    database_url: Optional[str] = typer.Option(
        None,
        "--database-url",
        envvar="DATABASE_URL_SYNC",
        help="Synchronous PostgreSQL connection URL (psycopg2). Defaults to DATABASE_URL_SYNC env var.",
    ),
) -> None:
    """Seed the CivPulse Geo database with Bibb County GIS data and synthetic addresses."""
    geojson_path = geojson or DEFAULT_GEOJSON

    if not geojson_path.exists():
        typer.echo(f"GeoJSON file not found: {geojson_path}", err=True)
        raise typer.Exit(code=1)

    db_url = database_url or settings.database_url_sync
    typer.echo(f"Connecting to database: {db_url.split('@')[-1]}")  # hide credentials

    engine = create_engine(db_url)

    with engine.connect() as conn:
        # Load GeoJSON addresses
        addr_count, geo_count = load_geojson_addresses(geojson_path, conn)
        typer.echo(f"GeoJSON: {addr_count} address rows processed, {geo_count} geocoding results inserted")

        # Load synthetic edge cases
        synthetic_count = load_synthetic_addresses(conn)
        typer.echo(f"Synthetic: {synthetic_count} address rows processed")

        conn.commit()

    typer.echo("Seed complete.")


if __name__ == "__main__":
    app()
