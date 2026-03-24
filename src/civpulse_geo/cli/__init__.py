"""CivPulse Geo CLI -- GIS data import tools.

Provides the `geo-import` entry point for loading GeoJSON, KML, and SHP files
as provider geocoding results and auto-setting OfficialGeocoding records.
"""
from __future__ import annotations

import csv
import gzip
import io
import json
import subprocess
import time
import zipfile
from pathlib import Path

import typer
import usaddress
from loguru import logger
from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn, TimeElapsedColumn
from sqlalchemy import create_engine, text

from civpulse_geo.cli.parsers import load_geojson, load_kml, load_shp
from civpulse_geo.config import settings
from civpulse_geo.normalization import canonical_key, parse_address_components

app = typer.Typer(help="CivPulse Geo CLI -- GIS data import tools.")

OA_BATCH_SIZE = 1000
NAD_BATCH_SIZE = 50_000  # Rows per COPY+upsert cycle

NAD_COPY_SQL = """
    COPY nad_temp (
        source_hash, street_number, street_name, street_suffix,
        unit, city, state, zip_code, location, placement
    ) FROM STDIN WITH (FORMAT CSV, NULL '')
"""

NAD_UPSERT_SQL = """
    INSERT INTO nad_points (
        source_hash, street_number, street_name, street_suffix,
        unit, city, state, zip_code, location, placement
    )
    SELECT
        source_hash, street_number, street_name, street_suffix,
        unit, city, state, zip_code,
        ST_GeogFromText(location),
        placement
    FROM nad_temp
    ON CONFLICT ON CONSTRAINT uq_nad_source_hash DO UPDATE
        SET street_number = EXCLUDED.street_number,
            street_name   = EXCLUDED.street_name,
            street_suffix = EXCLUDED.street_suffix,
            unit          = EXCLUDED.unit,
            city          = EXCLUDED.city,
            state         = EXCLUDED.state,
            zip_code      = EXCLUDED.zip_code,
            location      = EXCLUDED.location,
            placement     = EXCLUDED.placement
"""

CREATE_NAD_TEMP_TABLE = """
    CREATE TEMP TABLE IF NOT EXISTS nad_temp (
        source_hash TEXT,
        street_number TEXT,
        street_name TEXT,
        street_suffix TEXT,
        unit TEXT,
        city TEXT,
        state TEXT,
        zip_code TEXT,
        location TEXT,
        placement TEXT
    )
"""

TRUNCATE_NAD_TEMP = "TRUNCATE nad_temp"

# ---------------------------------------------------------------------------
# Tiger geocoder — FIPS / abbreviation conversion
# ---------------------------------------------------------------------------

FIPS_TO_ABBREV: dict[str, str] = {
    "01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA",
    "08": "CO", "09": "CT", "10": "DE", "11": "DC", "12": "FL",
    "13": "GA", "15": "HI", "16": "ID", "17": "IL", "18": "IN",
    "19": "IA", "20": "KS", "21": "KY", "22": "LA", "23": "ME",
    "24": "MD", "25": "MA", "26": "MI", "27": "MN", "28": "MS",
    "29": "MO", "30": "MT", "31": "NE", "32": "NV", "33": "NH",
    "34": "NJ", "35": "NM", "36": "NY", "37": "NC", "38": "ND",
    "39": "OH", "40": "OK", "41": "OR", "42": "PA", "44": "RI",
    "45": "SC", "46": "SD", "47": "TN", "48": "TX", "49": "UT",
    "50": "VT", "51": "VA", "53": "WA", "54": "WV", "55": "WI",
    "56": "WY",
}

ABBREV_TO_FIPS: dict[str, str] = {v: k for k, v in FIPS_TO_ABBREV.items()}

TIGER_EXTENSIONS = [
    "fuzzystrmatch",
    "address_standardizer",
    "address_standardizer_data_us",
    "postgis_tiger_geocoder",
]


def _resolve_state(value: str) -> str | None:
    """Convert a FIPS code or state abbreviation to a 2-letter state abbreviation.

    Accepts:
    - 2-digit FIPS code (e.g., "13" -> "GA")
    - 2-letter abbreviation (e.g., "GA" -> "GA", case insensitive)

    Returns None if the value is unrecognized.
    """
    upper = value.strip().upper()
    # Check if it's a known abbreviation
    if upper in ABBREV_TO_FIPS:
        return upper
    # Check if it's a FIPS code (zero-pad to 2 digits)
    padded = value.strip().zfill(2)
    return FIPS_TO_ABBREV.get(padded)


@app.command("setup-tiger")
def setup_tiger(
    states: list[str] = typer.Argument(..., help="State FIPS codes or abbreviations (e.g., 13 for GA, or GA directly)"),
    database_url: str | None = typer.Option(
        None, "--database-url", envvar="DATABASE_URL_SYNC",
        help="Synchronous PostgreSQL URL (psycopg2).",
    ),
) -> None:
    """Install Tiger extensions and load TIGER/Line data for specified state(s).

    Accepts state FIPS codes (e.g., 13 for Georgia) or 2-letter abbreviations (e.g., GA).
    Fully idempotent: safe to re-run for already-installed extensions and loaded states.

    This command must run inside the Docker container where shp2pgsql and wget are available:
        docker compose exec db geo-import setup-tiger 13
    """
    # Step 1: Resolve FIPS codes to abbreviations
    abbrevs: list[str] = []
    for state in states:
        abbrev = _resolve_state(state)
        if abbrev is None:
            typer.echo(f"Error: unknown state identifier: {state}", err=True)
            raise typer.Exit(1)
        abbrevs.append(abbrev)

    db_url = database_url or settings.database_url_sync
    engine = create_engine(db_url)

    # Step 2: Install extensions (idempotent)
    typer.echo("Installing Tiger extensions...")
    with engine.connect() as conn:
        for ext in TIGER_EXTENSIONS:
            conn.execute(text(f"CREATE EXTENSION IF NOT EXISTS {ext}"))
        conn.commit()
    typer.echo("Tiger extensions installed.")

    # Step 3: Generate and execute loader script per state
    for abbrev in abbrevs:
        typer.echo(f"Generating loader script for {abbrev}...")
        with engine.connect() as conn:
            result = conn.execute(
                text("SELECT Loader_Generate_Script(ARRAY[:state], 'sh')"),
                {"state": abbrev},
            )
            script_text = result.scalar()

        if not script_text:
            typer.echo(f"Warning: Loader_Generate_Script returned empty for {abbrev}", err=True)
            continue

        typer.echo(f"Executing loader script for {abbrev}...")
        proc = subprocess.run(
            ["bash", "-c", script_text],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            typer.echo(f"Error loading {abbrev}: {proc.stderr}", err=True)
            raise typer.Exit(1)
        typer.echo(f"Tiger data loaded for {abbrev}.")

    typer.echo("setup-tiger complete.")

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


def _parse_street_components(street: str) -> tuple[str, str | None]:
    """Extract street_name and street_suffix from OA street field using usaddress."""
    if not street:
        return street or "", None
    tokens = usaddress.parse(street)
    name_parts = [tok for tok, lbl in tokens if lbl == "StreetName"]
    suffix_parts = [tok for tok, lbl in tokens if lbl == "StreetNamePostType"]
    street_name = " ".join(name_parts) if name_parts else street
    street_suffix = suffix_parts[0] if suffix_parts else None
    return street_name, street_suffix


def _parse_oa_feature(feat: dict, stats: dict) -> dict | None:
    """Parse an OA GeoJSON feature into a dict suitable for DB insert.

    Returns None and increments stats["skipped"] if the feature is invalid.
    """
    props = feat.get("properties", {})
    geom = feat.get("geometry")

    # Validate coordinates
    if not geom or not geom.get("coordinates") or len(geom["coordinates"]) < 2:
        stats["skipped"] += 1
        source_hash = (props or {}).get("hash", "unknown")
        logger.warning(f"Feature skipped (missing coordinates): hash={source_hash}")
        return None

    lng, lat = geom["coordinates"][0], geom["coordinates"][1]

    # Validate numeric coordinates
    if not isinstance(lng, (int, float)) or not isinstance(lat, (int, float)):
        stats["skipped"] += 1
        return None

    # Require source_hash for deduplication
    source_hash = props.get("hash", "")
    if not source_hash:
        stats["skipped"] += 1
        return None

    # Parse street components
    street_name, street_suffix = _parse_street_components(props.get("street", "") or "")

    return {
        "source_hash": source_hash,
        "street_number": props.get("number") or None,
        "street_name": street_name or None,
        "street_suffix": street_suffix,
        "unit": props.get("unit") or None,
        "city": props.get("city") or None,
        "district": props.get("district") or None,
        "region": props.get("region") or None,
        "postcode": props.get("postcode") or None,
        "location": f"SRID=4326;POINT({lng} {lat})",
        "accuracy": props.get("accuracy") or None,
    }


def _upsert_oa_batch(conn, batch: list[dict], stats: dict) -> None:
    """Upsert a batch of OA rows into openaddresses_points using ON CONFLICT."""
    for row in batch:
        result = conn.execute(
            text("""
                INSERT INTO openaddresses_points (
                    source_hash, street_number, street_name, street_suffix,
                    unit, city, district, region, postcode, location, accuracy
                ) VALUES (
                    :source_hash, :street_number, :street_name, :street_suffix,
                    :unit, :city, :district, :region, :postcode,
                    ST_GeogFromText(:location), :accuracy
                )
                ON CONFLICT ON CONSTRAINT uq_oa_source_hash DO UPDATE
                    SET street_number = EXCLUDED.street_number,
                        street_name   = EXCLUDED.street_name,
                        street_suffix = EXCLUDED.street_suffix,
                        unit          = EXCLUDED.unit,
                        city          = EXCLUDED.city,
                        district      = EXCLUDED.district,
                        region        = EXCLUDED.region,
                        postcode      = EXCLUDED.postcode,
                        location      = EXCLUDED.location,
                        accuracy      = EXCLUDED.accuracy
                RETURNING (xmax = 0) AS was_inserted
            """),
            row,
        )
        was_inserted = result.scalar()
        if was_inserted:
            stats["inserted"] += 1
        else:
            stats["updated"] += 1
    conn.commit()


@app.command("load-oa")
def load_openaddresses(
    file: Path = typer.Argument(..., help="Path to OpenAddresses .geojson.gz file"),
    database_url: str | None = typer.Option(
        None, "--database-url", envvar="DATABASE_URL_SYNC",
        help="Synchronous PostgreSQL URL (psycopg2).",
    ),
) -> None:
    """Import an OpenAddresses .geojson.gz file into the openaddresses_points staging table."""
    if not file.exists():
        typer.echo(f"Error: file not found: {file}", err=True)
        raise typer.Exit(1)
    if not str(file).endswith(".geojson.gz"):
        typer.echo(f"Error: expected .geojson.gz file, got: {file.suffix}", err=True)
        raise typer.Exit(1)

    db_url = database_url or settings.database_url_sync
    engine = create_engine(db_url)
    start_time = time.time()
    stats = {"processed": 0, "inserted": 0, "updated": 0, "skipped": 0}

    # Two-pass: count lines first for progress bar
    logger.info(f"Counting records in {file}...")
    total_lines = sum(1 for _ in gzip.open(file, "rt"))
    logger.info(f"Found {total_lines} records")

    with engine.connect() as conn:
        batch: list[dict] = []
        with Progress(
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
        ) as progress:
            task = progress.add_task("Importing OA data...", total=total_lines)
            with gzip.open(file, "rt") as f:
                for line in f:
                    stats["processed"] += 1
                    try:
                        feat = json.loads(line)
                    except json.JSONDecodeError:
                        stats["skipped"] += 1
                        logger.warning(
                            f"Malformed JSON line skipped at record {stats['processed']}"
                        )
                        progress.advance(task)
                        continue

                    row = _parse_oa_feature(feat, stats)
                    if row:
                        batch.append(row)

                    if len(batch) >= OA_BATCH_SIZE:
                        _upsert_oa_batch(conn, batch, stats)
                        batch.clear()

                    progress.advance(task)

                # Flush remaining batch
                if batch:
                    _upsert_oa_batch(conn, batch, stats)

    elapsed = time.time() - start_time
    typer.echo(f"\nImport complete in {elapsed:.1f}s")
    typer.echo(f"  Processed: {stats['processed']}")
    typer.echo(f"  Inserted:  {stats['inserted']}")
    typer.echo(f"  Updated:   {stats['updated']}")
    typer.echo(f"  Skipped:   {stats['skipped']}")


def _resolve_city(post_city: str, inc_muni: str, county: str) -> str | None:
    """Apply NAD city fallback chain: Post_City -> Inc_Muni -> County.

    Skips values that are empty or case-insensitive "not stated".
    """
    for raw in [post_city, inc_muni, county]:
        val = (raw or "").strip()
        if val and val.lower() != "not stated":
            return val
    return None


def _parse_nad_row(row: dict, stats: dict) -> list[str] | None:
    """Parse a NAD CSV row dict into a list of 10 values for COPY CSV format.

    Returns None and increments stats["skipped"] if the row has invalid coordinates.
    Column order matches NAD_COPY_SQL: source_hash, street_number, street_name,
    street_suffix, unit, city, state, zip_code, location, placement.
    """
    lng_str = (row.get("Longitude") or "").strip()
    lat_str = (row.get("Latitude") or "").strip()
    if not lng_str or not lat_str:
        stats["skipped"] += 1
        return None
    try:
        float(lng_str)
        float(lat_str)
    except ValueError:
        stats["skipped"] += 1
        return None

    uuid_raw = row.get("UUID", "")
    source_hash = uuid_raw.strip().strip("{}")

    if not source_hash:
        stats["skipped"] += 1
        return None

    city = _resolve_city(
        row.get("Post_City", ""),
        row.get("Inc_Muni", ""),
        row.get("County", ""),
    )

    return [
        source_hash,
        (row.get("Add_Number") or "").strip() or "",
        (row.get("St_Name") or "").strip() or "",
        (row.get("St_PosTyp") or "").strip() or "",
        (row.get("Unit") or "").strip() or "",
        city or "",
        (row.get("State") or "").strip() or "",
        (row.get("Zip_Code") or "").strip() or "",
        f"SRID=4326;POINT({lng_str} {lat_str})",
        (row.get("Placement") or "").strip() or "",
    ]


def _flush_nad_batch(conn, buf: io.StringIO, stats: dict) -> None:
    """COPY a batch from StringIO buffer into nad_temp, then upsert into nad_points."""
    buf.seek(0)
    raw_conn = conn.connection
    with raw_conn.cursor() as cur:
        cur.execute(TRUNCATE_NAD_TEMP)
        cur.copy_expert(NAD_COPY_SQL, buf)
        cur.execute(NAD_UPSERT_SQL)
        upserted = cur.rowcount
        stats["upserted"] += upserted
    raw_conn.commit()


@app.command("load-nad")
def load_nad(
    file: Path = typer.Argument(..., help="Path to NAD r21 CSV ZIP file"),
    states: list[str] = typer.Option(
        ..., "--state", "-s",
        help="State abbreviation(s) or FIPS code(s) to import (required). E.g. --state GA --state FL",
    ),
    database_url: str | None = typer.Option(
        None, "--database-url", envvar="DATABASE_URL_SYNC",
        help="Synchronous PostgreSQL URL (psycopg2).",
    ),
) -> None:
    """Import NAD r21 CSV data from ZIP into nad_points via PostgreSQL COPY.

    Accepts the NAD_r21_TXT.zip file directly. Streams the CSV from inside the ZIP
    without extracting to disk. Filters rows by the required --state argument(s).
    Uses COPY to a temp table then INSERT...ON CONFLICT for idempotent upsert.
    """
    if not file.exists():
        typer.echo(f"Error: file not found: {file}", err=True)
        raise typer.Exit(1)

    # Resolve state arguments
    state_abbrevs: set[str] = set()
    for s in states:
        abbrev = _resolve_state(s)
        if abbrev is None:
            typer.echo(f"Error: unknown state identifier: {s}", err=True)
            raise typer.Exit(1)
        state_abbrevs.add(abbrev.upper())

    db_url = database_url or settings.database_url_sync
    engine = create_engine(db_url)
    start_time = time.time()
    stats = {"processed": 0, "imported": 0, "skipped": 0, "upserted": 0}

    # Find the TXT file inside the ZIP
    with zipfile.ZipFile(file, "r") as zf:
        txt_files = [n for n in zf.namelist() if n.lower().endswith(".txt") and "schema" not in n.lower()]
        if not txt_files:
            typer.echo("Error: no TXT data file found in ZIP", err=True)
            raise typer.Exit(1)
        txt_name = txt_files[0]
        logger.info(f"Reading {txt_name} from {file}")

        # Count rows for progress bar (state-filtered)
        typer.echo(f"Counting rows for state(s): {', '.join(sorted(state_abbrevs))}...")
        total_rows = 0
        with zf.open(txt_name) as raw_f:
            text_f = io.TextIOWrapper(raw_f, encoding="utf-8-sig")
            reader = csv.DictReader(text_f)
            for row in reader:
                if (row.get("State") or "").strip().upper() in state_abbrevs:
                    total_rows += 1
        typer.echo(f"Found {total_rows} rows for {', '.join(sorted(state_abbrevs))}")

        if total_rows == 0:
            typer.echo("No matching rows found. Nothing to import.")
            raise typer.Exit(0)

        # Import pass
        with engine.connect() as conn:
            raw_conn = conn.connection
            with raw_conn.cursor() as cur:
                cur.execute(CREATE_NAD_TEMP_TABLE)
            raw_conn.commit()

            with Progress(
                TextColumn("[bold blue]{task.description}"),
                BarColumn(),
                MofNCompleteColumn(),
                TimeElapsedColumn(),
            ) as progress:
                task = progress.add_task("Importing NAD data...", total=total_rows)

                with zf.open(txt_name) as raw_f:
                    text_f = io.TextIOWrapper(raw_f, encoding="utf-8-sig")
                    reader = csv.DictReader(text_f)
                    batch_buf = io.StringIO()
                    batch_writer = csv.writer(batch_buf)
                    batch_count = 0

                    for row in reader:
                        row_state = (row.get("State") or "").strip().upper()
                        if row_state not in state_abbrevs:
                            continue

                        stats["processed"] += 1
                        parsed = _parse_nad_row(row, stats)
                        if parsed is None:
                            progress.advance(task)
                            continue

                        batch_writer.writerow(parsed)
                        batch_count += 1

                        if batch_count >= NAD_BATCH_SIZE:
                            _flush_nad_batch(conn, batch_buf, stats)
                            batch_buf = io.StringIO()
                            batch_writer = csv.writer(batch_buf)
                            batch_count = 0

                        progress.advance(task)

                    # Flush remaining
                    if batch_count > 0:
                        _flush_nad_batch(conn, batch_buf, stats)

    elapsed = time.time() - start_time
    typer.echo(f"\nImport complete in {elapsed:.1f}s")
    typer.echo(f"  Processed: {stats['processed']}")
    typer.echo(f"  Upserted:  {stats['upserted']}")
    typer.echo(f"  Skipped:   {stats['skipped']}")
