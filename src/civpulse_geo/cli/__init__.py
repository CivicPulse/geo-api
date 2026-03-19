"""CivPulse Geo CLI -- GIS data import tools.

Provides the `geo-import` entry point for loading GeoJSON, KML, and SHP files
as provider geocoding results and auto-setting OfficialGeocoding records.
"""
from __future__ import annotations

import json
from pathlib import Path

import typer
from loguru import logger
from sqlalchemy import create_engine, text

from civpulse_geo.cli.parsers import load_geojson, load_kml, load_shp
from civpulse_geo.config import settings
from civpulse_geo.normalization import canonical_key, parse_address_components

app = typer.Typer(help="CivPulse Geo CLI -- GIS data import tools.")

# Bibb County GeoJSON/KML field mapping
BIBB_FIELD_MAP = {
    "full_address": "FULLADDR",
    "city": "City_1",
    "zip_code": "ZIP_1",
    "state": "GA",  # Hardcoded for Bibb County, Georgia
}


@app.command("import")
def import_gis(
    file: Path = typer.Argument(..., help="GeoJSON, KML, or SHP file to import"),
    database_url: str | None = typer.Option(
        None, "--database-url", envvar="DATABASE_URL_SYNC",
        help="Synchronous PostgreSQL URL (psycopg2)."
    ),
    provider: str = typer.Option(
        "bibb_county_gis", "--provider",
        help="Provider name for imported geocoding records."
    ),
) -> None:
    """Import GIS address data as geocoding results for a provider.

    DATA-03 operational constraint: GIS data MUST be imported before the API
    geocodes addresses for the same locations. The OfficialGeocoding INSERT uses
    ON CONFLICT (address_id) DO NOTHING, so any existing official record is
    preserved. If census geocoding runs first, county GIS will not displace it.
    Use PUT /geocode/{hash}/official to correct the record when ordering is
    violated.
    """
    db_url = database_url or settings.database_url_sync

    # Auto-detect format from file extension
    suffix = file.suffix.lower()
    if suffix == ".geojson":
        features = load_geojson(file)
    elif suffix == ".kml":
        features = load_kml(file)
    elif suffix == ".shp":
        features = load_shp(file)
    else:
        typer.echo(
            f"Unsupported file format: {suffix}. Use .geojson, .kml, or .shp",
            err=True,
        )
        raise typer.Exit(1)

    typer.echo(f"Loaded {len(features)} features from {file.name}")

    engine = create_engine(db_url)
    stats: dict[str, int] = {
        "total": 0,
        "inserted": 0,
        "updated": 0,
        "skipped": 0,
        "errors": 0,
    }

    with engine.connect() as conn:
        for i, feature in enumerate(features, 1):
            stats["total"] += 1
            try:
                _import_feature(conn, feature, provider, stats)
            except Exception as exc:
                stats["errors"] += 1
                logger.warning(f"Feature {i}: {exc}")

            if i % 100 == 0:
                conn.commit()
                typer.echo(f"  Processed {i}/{len(features)}...")

        conn.commit()

    typer.echo("\nImport complete:")
    typer.echo(f"  Total:    {stats['total']}")
    typer.echo(f"  Inserted: {stats['inserted']}")
    typer.echo(f"  Updated:  {stats['updated']}")
    typer.echo(f"  Skipped:  {stats['skipped']}")
    typer.echo(f"  Errors:   {stats['errors']}")


def _import_feature(
    conn,
    feature: dict,
    provider: str,
    stats: dict[str, int],
) -> None:
    """Import a single GIS feature into the database (upsert logic).

    Steps:
    1. Extract address fields from feature properties.
    2. Skip if required fields are missing or no geometry.
    3. Upsert address row (INSERT ON CONFLICT DO NOTHING).
    4. Upsert geocoding_result row (INSERT ON CONFLICT DO UPDATE).
    5. Auto-set OfficialGeocoding if no admin_override exists for the address.
    """
    props = feature.get("properties", {})
    geometry = feature.get("geometry") or {}

    # Extract Bibb County GeoJSON/KML address fields
    fulladdr = (props.get("FULLADDR") or "").strip()
    city = (props.get("City_1") or "").strip()
    zip_code = (props.get("ZIP_1") or "").strip()
    state = "GA"

    if not fulladdr:
        stats["skipped"] += 1
        return

    coords = geometry.get("coordinates")
    if not coords or len(coords) < 2:
        stats["skipped"] += 1
        return

    lng, lat = float(coords[0]), float(coords[1])

    # Build freeform address for normalization
    freeform = f"{fulladdr}, {city}, {state} {zip_code}".strip(", ")
    normalized, address_hash = canonical_key(freeform)
    components = parse_address_components(freeform)

    # ── Step 1: Upsert address ───────────────────────────────────────────────
    address_id = _upsert_address(conn, freeform, normalized, address_hash, components)
    if address_id is None:
        stats["errors"] += 1
        return

    # ── Step 2: Upsert geocoding_result ─────────────────────────────────────
    wkt = f"SRID=4326;POINT({lng} {lat})"
    raw = json.dumps({"source": "bibb_county_gis_import", "original_coords": [lng, lat]})

    result = conn.execute(
        text("""
            INSERT INTO geocoding_results (
                address_id, provider_name, location, latitude, longitude,
                location_type, confidence, raw_response
            ) VALUES (
                :address_id, :provider,
                ST_GeogFromText(:location),
                :lat, :lng,
                'ROOFTOP', 1.0, :raw
            )
            ON CONFLICT ON CONSTRAINT uq_geocoding_address_provider DO UPDATE
                SET location      = ST_GeogFromText(:location),
                    latitude      = :lat,
                    longitude     = :lng,
                    location_type = 'ROOFTOP',
                    confidence    = 1.0,
                    raw_response  = :raw
            RETURNING id, (xmax = 0) AS was_inserted
        """),
        {
            "address_id": address_id,
            "provider": provider,
            "location": wkt,
            "lat": lat,
            "lng": lng,
            "raw": raw,
        },
    )
    row = result.fetchone()
    if row:
        geocoding_result_id = row[0]
        was_inserted = bool(row[1])
        if was_inserted:
            stats["inserted"] += 1
        else:
            stats["updated"] += 1
    else:
        stats["errors"] += 1
        return

    # ── Step 3: Auto-set OfficialGeocoding (if no admin override exists) ────
    override_row = conn.execute(
        text("SELECT id FROM admin_overrides WHERE address_id = :aid"),
        {"aid": address_id},
    ).fetchone()

    if override_row is None:
        # No admin override -- safe to auto-set official.
        # DATA-03 operational constraint: ON CONFLICT DO NOTHING means the
        # first writer wins. GIS import must run before API geocoding so that
        # county data becomes the default official. If ordering is violated,
        # use PUT /geocode/{hash}/official to correct the record.
        conn.execute(
            text("""
                INSERT INTO official_geocoding (address_id, geocoding_result_id)
                VALUES (:address_id, :geocoding_result_id)
                ON CONFLICT (address_id) DO NOTHING
            """),
            {"address_id": address_id, "geocoding_result_id": geocoding_result_id},
        )


def _upsert_address(
    conn,
    original_input: str,
    normalized_address: str,
    address_hash: str,
    components: dict,
) -> int | None:
    """Insert address row or retrieve existing id on hash conflict."""
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
