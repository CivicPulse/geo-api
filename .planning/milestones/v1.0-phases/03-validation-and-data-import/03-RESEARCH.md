# Phase 3: Validation and Data Import - Research

**Researched:** 2026-03-19
**Domain:** USPS address validation (scourgify), CLI GIS data import (GeoJSON/KML/SHP), SQLAlchemy ORM, Alembic migrations, Typer CLI
**Confidence:** HIGH — all key claims verified against live code and running tests

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Validation Provider Strategy**
- Scourgify-only for v1 — no external USPS v3 API dependency
- ZIP+4 delivery point validation (VAL-06) returns `delivery_point_verified: false` in scourgify-only mode
- Unparseable addresses return HTTP 422 — invalid input is an error, not a low-confidence result
- Validation endpoint is independent from geocoding — no coupling, no optional geocode flag

**Validation Response Design**
- Structured field input (VAL-03) is concatenated to a freeform string and run through the same scourgify pipeline as freeform input (VAL-02) — one code path
- Full structured response per candidate: `normalized_address` + parsed components + `confidence` + `delivery_point_verified` + `provider_name`
- Validation results cached in a `validation_results` table — same pattern as `geocoding_results`
- Single candidate from scourgify for v1; response schema supports `candidates[]` array for future multi-candidate providers

**GIS Import CLI Workflow**
- CLI tool lives in `src/civpulse_geo/cli/` module
- Single `import` command auto-detects file format from extension (.geojson, .kml, .shp)
- Uses appropriate parser per format: `json` for GeoJSON, `fiona`/`geopandas` for KML and SHP
- Summary output with counts: total records, inserted, updated (upserted), skipped (unparseable), errors
- Hardcoded Bibb County field mapping: `FULLADDR`, `ADDNUM`, `STNAME`, `STTYPE`, `MUNICIPALITY`, `STATE`, `ZIPCODE` → address components
- Creates new Address records for GIS entries not already in the database

**County Data as Default Official**
- Auto-set `OfficialGeocoding` at import time: if no row exists AND no `AdminOverride` exists, create one pointing to the bibb_county_gis result
- Never overwrite admin overrides on re-import — admin decisions are final
- Priority chain: `AdminOverride` > admin-set `OfficialGeocoding` > bibb_county_gis auto-set `OfficialGeocoding` > other provider results

### Claude's Discretion
- Exact `ValidationResult` dataclass field design for the provider contract
- Alembic migration structure for validation_results table
- Fiona/geopandas dependency choice for KML/SHP parsing
- Test fixture organization for validation and import tests
- CLI argument naming and help text
- Confidence score assignment for scourgify results

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| VAL-01 | API can validate a single US address and return USPS-standardized corrected address(es) | Scourgify `normalize_address_record()` verified to return USPS Pub 28 normalized output |
| VAL-02 | API accepts freeform string input for validation | Scourgify accepts bare freeform strings directly |
| VAL-03 | API accepts structured field input (street, city, state, zip as separate fields) | Concatenate to freeform; scourgify handles; one code path |
| VAL-04 | API returns all possible corrected addresses ranked with confidence scores | Scourgify returns one result; confidence=1.0 on success; schema supports `candidates[]` |
| VAL-05 | API normalizes address components to USPS standards (abbreviations, casing, formatting) | Verified: "Road" -> "RD", "Georgia" -> "GA", all-caps output |
| VAL-06 | API performs ZIP+4 delivery point validation | Returns `delivery_point_verified: false` in scourgify-only mode (by design decision) |
| DATA-01 | CLI tool can bulk import GeoJSON, KML, SHP files as provider geocode results | GeoJSON: stdlib json; KML: stdlib xml.etree; SHP: fiona required (CRS reprojection needed) |
| DATA-02 | Imported data stored as provider "bibb_county_gis" using same schema as online results | Uses existing `geocoding_results` table with `provider_name="bibb_county_gis"` |
| DATA-03 | When bibb_county_gis data exists and no admin override, county data is default official | `OfficialGeocoding` upsert with `ON CONFLICT DO NOTHING` for address_id — only set if not yet set |
| DATA-04 | CLI import supports re-importing without creating duplicates (upsert) | PostgreSQL `INSERT ... ON CONFLICT DO UPDATE` on `uq_geocoding_address_provider` constraint |
</phase_requirements>

---

## Summary

Phase 3 adds two independent vertical slices on top of the Phase 1/2 foundation: (1) a validation API endpoint that normalizes US addresses via scourgify and returns USPS-standardized candidates, and (2) a CLI import tool that loads Bibb County GIS data files as first-class geocoding provider results that auto-become the default official geocode.

Both slices follow patterns already established in the codebase. The validation slice mirrors the geocoding service architecture (ValidationProvider ABC → ScourgifyValidationProvider → ValidationService → validation router). The import CLI extends `scripts/seed.py` into a proper Typer package with upsert semantics and OfficialGeocoding auto-setting.

**Critical discovery:** The sample SHP file uses NAD83 State Plane Georgia West FIPS 1002 (US Survey Feet, EPSG:2240) — NOT WGS84. Coordinates `x=2,457,949 / y=1,032,659` are projected feet and must be reprojected to WGS84 lat/lng before storing. `fiona` reads SHP files with built-in CRS metadata and can reproject to WGS84 via its `crs_wkt` / `transform` support (which uses PROJ under the hood). This makes fiona a hard requirement for SHP format. GeoJSON and KML already have WGS84 coordinates and need no reprojection.

**Primary recommendation:** Follow established patterns closely. The new code should be nearly isomorphic to the geocoding layer — different data shapes but identical structural patterns.

---

## Standard Stack

### Core (already installed — no new additions needed for validation)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| usaddress-scourgify | 0.6.0 | USPS address normalization — the validation engine | Already a project dependency; generates USPS Pub 28 normalized forms |
| fastapi | 0.135.1+ | Validation router, Pydantic request/response models | Project standard; consistent with geocoding router |
| sqlalchemy | 2.0.48+ | ORM for `validation_results` table | Project standard; already used for geocoding_results |
| alembic | 1.18.4+ | Migration for `validation_results` table | Project standard; already handles existing schema |
| typer | 0.24.1+ | CLI entry point for import tool | Project standard; already used in seed.py |
| loguru | 0.7.3+ | CLI and service logging | Project standard |

### New Dependency (required for SHP format)
| Library | Version | Purpose | Why Needed |
|---------|---------|---------|------------|
| fiona | latest | SHP + KML file reading with CRS metadata | SHP uses EPSG:2240 (NAD83 State Plane, US Survey Feet) — fiona handles CRS reprojection to WGS84 |

**Important:** `geopandas` is NOT needed. fiona alone provides CRS-aware SHP/KML reading. geopandas adds pandas, numpy, scipy — unnecessary weight for a CLI import tool.

### Supporting (for SHP only)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pyproj | bundled with fiona | Coordinate reprojection EPSG:2240 -> EPSG:4326 | SHP import only; fiona exposes it via `fiona.transform.transform_geom()` |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| fiona | geopandas | geopandas pulls in pandas/numpy/scipy — 100MB+ for no benefit in this use case |
| fiona | pyshp + pyproj separately | More code, no advantage; fiona already bundles pyproj and handles DBF+SHP together |
| fiona | stdlib struct + zipfile + pyproj | Significant manual work to parse DBF field layout and SHP binary records; fiona is the right tool |
| stdlib xml (KML) | fiona | fiona supports KML via GDAL driver; but stdlib xml works fine and avoids a dependency for one format |

**Recommended parser strategy:**
- GeoJSON: `stdlib json` (already demonstrated in seed.py, no new code needed)
- KML: `stdlib xml.etree.ElementTree` (verified working, no fiona needed for KML)
- SHP: `fiona` (hard requirement due to CRS reprojection)

**Installation:**
```bash
uv add fiona
```

**Version verification:**
```bash
uv run python -c "import fiona; print(fiona.__version__)"
```

---

## Architecture Patterns

### Recommended Project Structure
```
src/civpulse_geo/
├── api/
│   ├── geocoding.py     # existing
│   ├── health.py        # existing
│   └── validation.py    # NEW: POST /validate router
├── cli/
│   └── __init__.py      # NEW: Typer app for import command
├── models/
│   ├── geocoding.py     # existing (reused as-is)
│   └── validation.py    # NEW: ValidationResult ORM model
├── providers/
│   ├── base.py          # existing (ValidationProvider ABC already defined)
│   ├── census.py        # existing
│   └── scourgify.py     # NEW: ScourgifyValidationProvider
├── schemas/
│   ├── geocoding.py     # existing
│   └── validation.py    # NEW: ValidateRequest/ValidateResponse Pydantic models
└── services/
    ├── geocoding.py     # existing
    └── validation.py   # NEW: ValidationService (cache-first pipeline)
```

**Migration:**
```
alembic/versions/
└── XXXX_add_validation_results_table.py   # NEW: validation_results table
```

**CLI:**
```
src/civpulse_geo/cli/__init__.py  # Typer app with `import` command
```

**pyproject.toml CLI entry point:**
```toml
[project.scripts]
geo-import = "civpulse_geo.cli:app"
```

---

### Pattern 1: ValidationProvider Contract

The `ValidationProvider` ABC is already defined in `providers/base.py`. The contract returns `dict` from `validate()`. For the ScourgifyValidationProvider, the dict should be a `ValidationResult` dataclass (Claude's discretion on exact fields).

**Recommended `ValidationResult` dataclass:**
```python
# src/civpulse_geo/providers/schemas.py (extend existing)
@dataclass
class ValidationResult:
    normalized_address: str          # Full USPS normalized string: "123 MAIN ST MACON GA 31201"
    address_line_1: str              # "123 MAIN ST"
    address_line_2: str | None       # "APT 4B" or None
    city: str | None                 # "MACON"
    state: str | None                # "GA"
    postal_code: str | None          # "31201" (ZIP5 from scourgify output, may include +4)
    confidence: float                # 1.0 for scourgify success (binary: parsed or not)
    delivery_point_verified: bool    # Always False for scourgify-only mode
    provider_name: str               # "scourgify"
    original_input: str              # Echo back the input for "did you mean?" UI
```

**Why confidence=1.0 for scourgify:** Scourgify is binary — either it parses the address (success) or raises `UnParseableAddressError` (→ 422). There are no partial matches. On success, the normalized form is correct. Confidence 1.0 accurately represents "this is USPS-valid."

---

### Pattern 2: ScourgifyValidationProvider (mirrors CensusGeocodingProvider)

```python
# src/civpulse_geo/providers/scourgify.py
from scourgify import normalize_address_record
from scourgify.exceptions import (
    UnParseableAddressError, AmbiguousAddressError,
    AddressNormalizationError, IncompleteAddressError,
)
from civpulse_geo.providers.base import ValidationProvider

SCOURGIFY_CONFIDENCE = 1.0

class ScourgifyValidationProvider(ValidationProvider):
    @property
    def provider_name(self) -> str:
        return "scourgify"

    async def validate(self, address: str) -> dict:
        # scourgify is synchronous — call directly (no I/O, no async needed)
        try:
            parsed = normalize_address_record(address)
        except (UnParseableAddressError, AmbiguousAddressError,
                AddressNormalizationError, IncompleteAddressError) as e:
            raise ProviderNetworkError(f"Address unparseable: {e}") from e
        # Build ValidationResult dataclass and return as dict or direct
        ...

    async def batch_validate(self, addresses: list[str]) -> list[dict]:
        results = []
        for addr in addresses:
            result = await self.validate(addr)
            results.append(result)
        return results
```

**Key insight:** scourgify is a pure-Python synchronous library with no I/O. Calling it from an `async def` method is correct — no `asyncio.to_thread()` needed. The provider interface is async to accommodate future real HTTP providers (USPS v3, Lob, SmartyStreets), but scourgify can be called inline.

**Verified scourgify output format:**
```python
normalize_address_record("123 Main Road, Macon, Georgia 31201-5678")
# Returns OrderedDict:
# address_line_1: "123 MAIN RD"    (Road -> RD, all caps)
# address_line_2: None
# city:           "MACON"
# state:          "GA"              (Georgia -> GA)
# postal_code:    "31201-5678"      (scourgify preserves ZIP+4 in postal_code)
```

**Important ZIP+4 note:** scourgify preserves ZIP+4 in `postal_code` if present in input. The normalization layer (`_zip5()` in `normalization.py`) already strips it for cache keys. For the validation response, the planner should decide whether to return the full `postal_code` from scourgify or strip to ZIP5. The existing `_zip5()` helper is available for this.

---

### Pattern 3: ValidationService (mirrors GeocodingService)

```python
# src/civpulse_geo/services/validation.py
class ValidationService:
    async def validate(
        self,
        freeform: str,
        db: AsyncSession,
        providers: dict[str, ValidationProvider],
    ) -> dict:
        # Step 1: Normalize and hash (reuse canonical_key())
        normalized, address_hash = canonical_key(freeform)

        # Step 2: Find or create Address record (same as GeocodingService)

        # Step 3: Cache check — query validation_results WHERE address_id AND provider_name

        # Step 4: Call provider on cache miss
        # provider.validate() raises ProviderNetworkError for unparseable -> 422 at router layer

        # Step 5: Upsert into validation_results (ON CONFLICT DO UPDATE)

        # Step 6: Commit and return

    async def validate_structured(
        self,
        street: str,
        city: str | None,
        state: str | None,
        zip_code: str | None,
        db: AsyncSession,
        providers: dict[str, ValidationProvider],
    ) -> dict:
        # Concatenate to freeform, delegate to validate()
        parts = [p for p in [street, city, state, zip_code] if p]
        freeform = ", ".join(parts)
        return await self.validate(freeform, db, providers)
```

---

### Pattern 4: validation_results Table (mirrors geocoding_results)

```python
# src/civpulse_geo/models/validation.py
class ValidationResult(Base, TimestampMixin):
    __tablename__ = "validation_results"
    __table_args__ = (
        UniqueConstraint(
            "address_id", "provider_name", name="uq_validation_address_provider"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    address_id: Mapped[int] = mapped_column(ForeignKey("addresses.id"), index=True)
    provider_name: Mapped[str] = mapped_column(String(50))
    normalized_address: Mapped[str | None] = mapped_column(Text)
    address_line_1: Mapped[str | None] = mapped_column(Text)
    address_line_2: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str | None] = mapped_column(String(2))
    postal_code: Mapped[str | None] = mapped_column(String(10))
    confidence: Mapped[float | None] = mapped_column(Float)
    delivery_point_verified: Mapped[bool] = mapped_column(default=False)
    raw_response: Mapped[dict | None] = mapped_column(JSON)
```

**Alembic migration note:** Based on Phase 1 lesson, autogenerate includes PostGIS TIGER extension tables. Manually review and remove any extension table DROP statements before committing. New Alembic migration chains from `b98c26825b02`.

---

### Pattern 5: GIS Import CLI

**File: `src/civpulse_geo/cli/__init__.py`**

```python
import typer
from pathlib import Path
from loguru import logger

app = typer.Typer(help="CivPulse Geo CLI — GIS data import tools.")

@app.command()
def import_gis(
    file: Path = typer.Argument(..., help="GeoJSON, KML, or SHP file to import"),
    database_url: str | None = typer.Option(None, "--database-url", envvar="DATABASE_URL_SYNC"),
    provider: str = typer.Option("bibb_county_gis", "--provider", help="Provider name"),
) -> None:
    """Import GIS address data as geocoding results."""
    # Auto-detect format from extension
    suffix = file.suffix.lower()
    if suffix == ".geojson":
        features = _load_geojson(file)
    elif suffix == ".kml":
        features = _load_kml(file)
    elif suffix == ".shp":
        features = _load_shp(file)  # requires fiona
    else:
        typer.echo(f"Unsupported format: {suffix}", err=True)
        raise typer.Exit(1)
    # ... upsert loop with progress counter
```

**Typer entry point registration in pyproject.toml:**
```toml
[project.scripts]
geo-import = "civpulse_geo.cli:app"
```

---

### Pattern 6: GeoJSON Field Mapping (Bibb County)

**Verified from live GeoJSON file inspection:**
```python
# Properties available in SAMPLE_Address_Points.geojson features
BIBB_GEOJSON_FIELD_MAP = {
    "FULLADDR": "full_address",    # "626 ARLINGTON PL" — primary field
    "City_1":   "city",            # "MACON"
    "ZIP_1":    "zip_code",        # "31201"
    # Geometry: feature["geometry"]["coordinates"] = [longitude, latitude]
    # ADDR_HN: house number (redundant with FULLADDR)
    # ADDR_SN: street name (redundant with FULLADDR)
    # ADDR_ST: street type (redundant with FULLADDR)
    # PREDIR / SUFDIR: directionals (redundant with FULLADDR)
}
# State is hardcoded: "GA" (Bibb County, Georgia)
# Build freeform: f"{FULLADDR}, {City_1}, GA {ZIP_1}"
```

**CONTEXT.md note on field mapping:** The CONTEXT mentions `FULLADDR`, `ADDNUM`, `STNAME`, `STTYPE`, `MUNICIPALITY`, `STATE`, `ZIPCODE` as the hardcoded mapping. However, the actual GeoJSON fields are `FULLADDR`, `City_1`, `ZIP_1` (no `ADDNUM`, `STNAME`, etc. as top-level fields — they exist as `ADDR_HN`, `ADDR_SN`, `ADDR_ST` but FULLADDR is the composite). The seed.py already demonstrates the correct approach: use `FULLADDR` + `City_1` + `ZIP_1` for the freeform address. The CONTEXT.md field names appear to describe semantic intent rather than exact property names.

---

### Pattern 7: KML Parsing (stdlib xml)

```python
import xml.etree.ElementTree as ET

def _load_kml(path: Path) -> list[dict]:
    ns = {"kml": "http://www.opengis.net/kml/2.2"}
    tree = ET.parse(path)
    root = tree.getroot()
    placemarks = root.findall(".//kml:Placemark", ns)
    features = []
    for pm in placemarks:
        coords_el = pm.find(".//kml:coordinates", ns)
        if coords_el is None:
            continue
        lng_str, lat_str = coords_el.text.strip().split(",")[:2]
        props = {}
        for sd in pm.findall(".//kml:SimpleData", ns):
            props[sd.get("name")] = sd.text
        features.append({
            "properties": props,
            "geometry": {"coordinates": [float(lng_str), float(lat_str)]}
        })
    return features
```

**Verified:** KML coordinates are already WGS84 (`-83.6412782,32.8379706`). Schema matches GeoJSON exactly (`FULLADDR`, `City_1`, `ZIP_1`). No CRS reprojection needed.

---

### Pattern 8: SHP Parsing (fiona required)

**Critical CRS finding:** The SHP file uses `PROJCS["NAD_1983_StatePlane_Georgia_West_FIPS_1002_Feet"...]` — EPSG:2240. Raw coordinates (`x=2,457,949 / y=1,032,659`) are in US Survey Feet, NOT lat/lng. Must reproject to EPSG:4326.

```python
import fiona
from fiona.transform import transform_geom

def _load_shp(path: Path) -> list[dict]:
    features = []
    with fiona.open(path) as src:
        src_crs = src.crs_wkt  # EPSG:2240 for this Bibb County file
        for feat in src:
            # Reproject geometry to WGS84
            geom_wgs84 = transform_geom(src.crs, "EPSG:4326", feat["geometry"])
            lng, lat = geom_wgs84["coordinates"]
            props = dict(feat["properties"])
            features.append({
                "properties": props,
                "geometry": {"coordinates": [lng, lat]}
            })
    return features
```

**Why fiona is mandatory for SHP:**
- Raw SHP coordinates are in EPSG:2240 (NAD83 State Plane Georgia West, US Survey Feet)
- Storing them without reprojection produces wildly wrong locations
- fiona reads the `.prj` file and exposes `src.crs` for transform
- pyshp (PyPI package `pyshp`) reads raw binary coordinates only — no CRS awareness
- `fiona.transform.transform_geom()` handles the EPSG:2240 → EPSG:4326 conversion

---

### Pattern 9: OfficialGeocoding Auto-Set at Import

```python
# At end of each record upsert in the import loop:
# 1. Upsert GeocodingResult (provider_name="bibb_county_gis")
# 2. Check if AdminOverride exists for this address_id
# 3. If no AdminOverride: upsert OfficialGeocoding with ON CONFLICT DO NOTHING
#    (do nothing if already set — preserves admin-set officials)

admin_check = conn.execute(
    text("SELECT id FROM admin_overrides WHERE address_id = :aid"),
    {"aid": address_id}
).fetchone()
if not admin_check:
    conn.execute(
        text("""
            INSERT INTO official_geocoding (address_id, geocoding_result_id)
            VALUES (:address_id, :geocoding_result_id)
            ON CONFLICT (address_id) DO NOTHING
        """),
        {"address_id": address_id, "geocoding_result_id": geocoding_result_id},
    )
```

**Why `ON CONFLICT DO NOTHING` (not `DO UPDATE`):** Admin-set `OfficialGeocoding` rows must not be overwritten. The unique constraint on `official_geocoding.address_id` means any existing row (whether auto-set or admin-set) blocks the insert. This correctly implements the priority chain: admin decisions survive re-import.

---

### Pattern 10: Validation Router (mirrors geocoding.py router)

```python
# src/civpulse_geo/api/validation.py
router = APIRouter(prefix="/validate", tags=["validation"])

@router.post("", response_model=ValidateResponse)
async def validate_address(
    body: ValidateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    service = ValidationService()
    try:
        result = await service.validate(
            freeform=body.address,  # or body.to_freeform() for structured input
            db=db,
            providers=request.app.state.validation_providers,
        )
    except ProviderNetworkError as e:
        raise HTTPException(status_code=422, detail=str(e))
    ...
```

**app.state.validation_providers:** Register separately from `app.state.providers` (geocoding providers). This avoids type confusion and is consistent with the existing `load_providers()` registry design which accepts `dict[str, type]`.

---

### Anti-Patterns to Avoid

- **Raising 422 from the service layer:** The service should raise `ProviderNetworkError` (or a new `AddressUnparseableError`); the router catches and maps to 422. Keep HTTP concerns in the router layer.
- **Storing ZIP+4 in the cache key hash:** `canonical_key()` already strips to ZIP5 — validation service should reuse it.
- **Calling `asyncio.to_thread()` for scourgify:** scourgify is pure Python with no GIL-releasing I/O — no thread needed; call inline.
- **Running re-import with ON CONFLICT DO UPDATE on OfficialGeocoding:** Would silently overwrite admin decisions. Always use DO NOTHING.
- **Storing SHP raw coordinates without reprojection:** Verify by checking `fiona.open(path).crs` at import time; log a warning if CRS is unexpected.
- **Not committing after each batch in CLI import:** For large files, commit every N records to avoid holding locks. For the sample files (17 records) this is fine, but the pattern matters for production imports.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| USPS abbreviation normalization | Custom suffix/state lookup tables | scourgify | Handles 500+ USPS Pub 28 abbreviations, directionals, state names, secondary designators |
| Coordinate reprojection | Manual math for NAD83 → WGS84 | fiona + PROJ | Map projections require ellipsoid parameters; manual conversion is error-prone |
| SHP/DBF binary parsing | struct-based DBF reader + SHP record parser | fiona | DBF field descriptors, null flags, encoding; SHP record headers, shape types — handled by fiona |
| Address component parsing | Regex-based address splitter | scourgify + existing `normalization.py` | scourgify is already doing this; `parse_address_components()` wraps it |
| Idempotent upsert | Check-then-insert logic | PostgreSQL `ON CONFLICT DO UPDATE` | Race conditions in check-then-insert; the DB constraint handles it atomically |
| Async-safe sessions | Manual session management | SQLAlchemy `AsyncSession` via `get_db()` dependency | Already established; don't create new sessions outside the DI chain |

**Key insight:** The most dangerous hand-roll pitfall here is coordinate reprojection. The SHP format requires knowing the source CRS and applying a mathematically correct transformation. fiona + PROJ handles this correctly; manual math introduces subtle errors.

---

## Common Pitfalls

### Pitfall 1: SHP Coordinate System Confusion
**What goes wrong:** Importing SHP without reprojecting gives `latitude=1032659, longitude=2457949` — thousands of meters from Georgia, nonsensical as WGS84.
**Why it happens:** The SHP file uses EPSG:2240 (NAD83 State Plane Georgia West, US Survey Feet). Raw x/y values are in feet from a false easting, not decimal degrees.
**How to avoid:** Always open SHP with fiona and check `src.crs`. If not EPSG:4326, reproject with `fiona.transform.transform_geom()`.
**Warning signs:** Coordinates outside [-180, 180] / [-90, 90] range; large integer-like numbers.

### Pitfall 2: scourgify postal_code Includes ZIP+4
**What goes wrong:** Storing the raw `postal_code` from scourgify in the validation result gives "31201-5678" when the address column is `String(5)`.
**Why it happens:** `normalize_address_record("789 Elm Rd, Macon, GA 31201-5678")` returns `postal_code: "31201-5678"` — scourgify preserves input ZIP+4.
**How to avoid:** Use the existing `_zip5()` helper from `normalization.py` to strip ZIP+4 when storing to the DB. Or store the full postal_code as-is in `validation_results` (the table's `postal_code` column should be `String(10)`, not `String(5)`).
**Warning signs:** Database errors on insert for long zip codes; mismatched cache hits.

### Pitfall 3: Overwriting AdminOverride on Re-Import
**What goes wrong:** Using `ON CONFLICT DO UPDATE` on `official_geocoding` would silently replace admin decisions with the auto-imported county data.
**Why it happens:** Easy to write a single upsert for all tables without distinguishing the importance of admin-set rows.
**How to avoid:** Check for `AdminOverride` row existence before inserting `OfficialGeocoding`. Use `ON CONFLICT (address_id) DO NOTHING` on `official_geocoding` always.
**Warning signs:** Admin override disappears after a re-import run.

### Pitfall 4: Validation Providers Not Registered in app.state
**What goes wrong:** `app.state.providers` currently contains only `GeocodingProvider` instances. Adding `ScourgifyValidationProvider` to the same dict would break the geocoding filter (`isinstance(provider, GeocodingProvider)`) in `GeocodingService`.
**Why it happens:** `load_providers()` is a generic registry; mixing provider types needs care.
**How to avoid:** Use a separate `app.state.validation_providers` dict. Register in `main.py` lifespan:
```python
app.state.validation_providers = load_providers({"scourgify": ScourgifyValidationProvider})
```
**Warning signs:** Census provider suddenly fails; wrong provider type returned.

### Pitfall 5: PO Box Inputs Silently Becoming 422
**What goes wrong:** PO Box addresses are unparseable by scourgify and raise `UnParseableAddressError`. If the 422 error message is generic, callers can't distinguish "address is wrong" from "PO Box not supported."
**Why it happens:** scourgify fundamentally cannot normalize PO Box addresses to USPS Pub 28 street form.
**How to avoid:** Include the scourgify exception message in the 422 detail. Document in API schema that PO Box addresses are not supported in v1.
**Warning signs:** Callers report 422 for valid PO Box addresses.

### Pitfall 6: Alembic Autogenerate Includes PostGIS Extension Tables
**What goes wrong:** `alembic revision --autogenerate` includes DROP statements for PostGIS TIGER extension tables in the downgrade path.
**Why it happens:** Known Phase 1 issue. Alembic sees PostGIS catalog tables and includes them.
**How to avoid:** After generating migration, manually review and remove any DROP statements for non-application tables before committing.
**Warning signs:** Downgrade drops `spatial_ref_sys` or `geography_columns`.

---

## Code Examples

### Scourgify Output Verification (live-tested)

```python
# Source: live test run in project environment 2026-03-19

normalize_address_record("626 Arlington Pl, Macon, GA 31201")
# -> {"address_line_1": "626 ARLINGTON PL", "address_line_2": None,
#     "city": "MACON", "state": "GA", "postal_code": "31201"}

normalize_address_record("123 Main Road, Macon, Georgia 31201")
# -> {"address_line_1": "123 MAIN RD", "address_line_2": None,
#     "city": "MACON", "state": "GA", "postal_code": "31201"}
# "Road" -> "RD", "Georgia" -> "GA"

normalize_address_record("100 Pine Street Apt 4B, Macon, GA 31201")
# -> {"address_line_1": "100 PINE ST", "address_line_2": "APT 4B",
#     "city": "MACON", "state": "GA", "postal_code": "31201"}
# unit moves to address_line_2

normalize_address_record("789 Elm Rd, Macon, Georgia 31201-5678")
# -> {"address_line_1": "789 ELM RD", ..., "postal_code": "31201-5678"}
# ZIP+4 preserved — use _zip5() helper for cache key

normalize_address_record("PO Box 123, Macon, GA 31201")
# -> raises UnParseableAddressError — caller must catch and return 422
```

### Validation Request/Response Pydantic Models

```python
# src/civpulse_geo/schemas/validation.py

from pydantic import BaseModel

class ValidateRequest(BaseModel):
    """Accept either freeform or structured — not both simultaneously."""
    address: str | None = None           # freeform: "123 Main St, Macon, GA 31201"
    street: str | None = None            # structured components
    city: str | None = None
    state: str | None = None
    zip_code: str | None = None

    def to_freeform(self) -> str:
        """Concatenate structured fields or return freeform directly."""
        if self.address:
            return self.address
        parts = [p for p in [self.street, self.city, self.state, self.zip_code] if p]
        return ", ".join(parts)

class ValidationCandidate(BaseModel):
    normalized_address: str
    address_line_1: str | None = None
    address_line_2: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    confidence: float
    delivery_point_verified: bool
    provider_name: str

class ValidateResponse(BaseModel):
    address_hash: str
    original_input: str
    candidates: list[ValidationCandidate]  # single-element for scourgify; multi for future
    cache_hit: bool
```

### GeocodingResult Upsert for bibb_county_gis (extend seed.py pattern)

```python
# Upsert pattern (same as GeocodingService, extended for bibb_county_gis)
# Source: src/civpulse_geo/services/geocoding.py lines 141-165

stmt = (
    pg_insert(GeocodingResultORM)
    .values(
        address_id=address_id,
        provider_name="bibb_county_gis",
        location=f"SRID=4326;POINT({lng} {lat})",
        latitude=lat,
        longitude=lng,
        location_type="ROOFTOP",   # county GIS parcel points are rooftop-level
        confidence=1.0,            # county official record — highest confidence
        raw_response={"source": "bibb_county_gis", "original_fields": props},
    )
    .on_conflict_do_update(
        constraint="uq_geocoding_address_provider",
        set_={
            "location": f"SRID=4326;POINT({lng} {lat})",
            "latitude": lat,
            "longitude": lng,
            "location_type": "ROOFTOP",
            "confidence": 1.0,
            "raw_response": {"source": "bibb_county_gis"},
        },
    )
    .returning(GeocodingResultORM.id)
)
```

### main.py Registration (validation providers)

```python
# src/civpulse_geo/main.py lifespan additions

from civpulse_geo.api import validation
from civpulse_geo.providers.scourgify import ScourgifyValidationProvider

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http_client = httpx.AsyncClient(timeout=10.0)
    app.state.providers = load_providers({"census": CensusGeocodingProvider})
    app.state.validation_providers = load_providers({"scourgify": ScourgifyValidationProvider})
    yield
    await app.state.http_client.aclose()

app.include_router(validation.router)
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| USPS v3 API for validation | scourgify library for v1 | v1 decision | No OAuth2 dependency; no breaking-change risk; free; works offline |
| geopandas for GIS files | fiona (standalone) for CLI import | Phase 3 decision | Eliminates pandas/numpy/scipy; ~90% smaller install |
| seed.py monolith for import | Typer CLI module in src/ | Phase 3 | Proper package location; importable; testable |
| Separate tables per provider type | Uniform geocoding_results + provider_name | Phase 1 design | bibb_county_gis reuses existing schema — zero schema duplication |

**Deprecated/outdated:**
- `scripts/seed.py`: The new CLI import tool in `src/civpulse_geo/cli/` supersedes seed.py's GeoJSON loader. seed.py can remain for synthetic test data but the production import path is the CLI tool.

---

## Open Questions

1. **fiona + KML: GDAL KML driver availability**
   - What we know: fiona supports KML via GDAL's KML driver; the sample KML is standard OGC KML 2.2
   - What's unclear: whether fiona's KML driver is enabled in the default fiona wheel
   - Recommendation: Use stdlib xml.etree for KML parsing (verified working) and fiona only for SHP. This avoids any GDAL driver uncertainty and reduces fiona's usage surface.

2. **Location type for bibb_county_gis results**
   - What we know: GIS parcel point data = rooftop-level accuracy
   - What's unclear: whether `LocationType.ROOFTOP` is the accurate choice vs `LocationType.APPROXIMATE`
   - Recommendation: Use `ROOFTOP` — county parcel centroid coordinates are typically more accurate than range interpolation

3. **Confidence score for ScourgifyValidationProvider**
   - What we know: scourgify is binary (success or exception); 1.0 on success is reasonable
   - What's unclear: whether callers will expect scores to reflect address completeness (e.g., 0.9 if no ZIP)
   - Recommendation: Use 1.0 uniformly for all scourgify successes (binary provider — no partial confidence); document this in API response

4. **Import CLI entry point registration**
   - What we know: pyproject.toml `[project.scripts]` registers a console entry point
   - What's unclear: whether the project convention is `uv run python -m civpulse_geo.cli` vs a named entry point
   - Recommendation: Add `[project.scripts]` entry point for consistency with the Typer CLI pattern used in seed.py (`uv run python scripts/seed.py`)

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 + pytest-asyncio 1.3.0 |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` — `asyncio_mode = "auto"`, `testpaths = ["tests"]` |
| Quick run command | `uv run pytest tests/ -x -q` |
| Full suite command | `uv run pytest tests/ -q` |

**Baseline confirmed:** 90 existing tests pass in 0.47s. New tests must not break this baseline.

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| VAL-01 | POST /validate returns 200 with normalized candidate | integration | `uv run pytest tests/test_validation_api.py -x` | ❌ Wave 0 |
| VAL-02 | Freeform string input accepted and normalized | unit | `uv run pytest tests/test_scourgify_provider.py::test_validate_freeform -x` | ❌ Wave 0 |
| VAL-03 | Structured field input concatenated and normalized | unit | `uv run pytest tests/test_scourgify_provider.py::test_validate_structured -x` | ❌ Wave 0 |
| VAL-04 | Response includes confidence score in candidates list | unit | `uv run pytest tests/test_validation_api.py::test_confidence_in_response -x` | ❌ Wave 0 |
| VAL-05 | "Road"→"RD", "Georgia"→"GA" normalization in response | unit | `uv run pytest tests/test_scourgify_provider.py::test_usps_abbreviations -x` | ❌ Wave 0 |
| VAL-06 | `delivery_point_verified: false` in all scourgify responses | unit | `uv run pytest tests/test_scourgify_provider.py::test_dpv_always_false -x` | ❌ Wave 0 |
| VAL-02 | Unparseable input returns 422 | integration | `uv run pytest tests/test_validation_api.py::test_unparseable_returns_422 -x` | ❌ Wave 0 |
| DATA-01 | CLI import loads GeoJSON file | unit | `uv run pytest tests/test_import_cli.py::test_import_geojson -x` | ❌ Wave 0 |
| DATA-01 | CLI import loads KML file | unit | `uv run pytest tests/test_import_cli.py::test_import_kml -x` | ❌ Wave 0 |
| DATA-01 | CLI import loads SHP file (with CRS reprojection) | unit | `uv run pytest tests/test_import_cli.py::test_import_shp -x` | ❌ Wave 0 |
| DATA-02 | Imported records have provider_name="bibb_county_gis" | unit | `uv run pytest tests/test_import_cli.py::test_provider_name -x` | ❌ Wave 0 |
| DATA-03 | OfficialGeocoding set at import when no override exists | unit | `uv run pytest tests/test_import_cli.py::test_official_set_on_import -x` | ❌ Wave 0 |
| DATA-03 | OfficialGeocoding NOT overwritten when admin override exists | unit | `uv run pytest tests/test_import_cli.py::test_official_not_overwritten -x` | ❌ Wave 0 |
| DATA-04 | Re-import same file: upserts not duplicates | unit | `uv run pytest tests/test_import_cli.py::test_upsert_idempotent -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/ -x -q`
- **Per wave merge:** `uv run pytest tests/ -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_scourgify_provider.py` — covers VAL-01 through VAL-06 provider unit tests
- [ ] `tests/test_validation_api.py` — covers VAL-01 through VAL-06 API integration tests
- [ ] `tests/test_validation_service.py` — covers ValidationService cache-first logic
- [ ] `tests/test_import_cli.py` — covers DATA-01 through DATA-04
- [ ] `alembic/versions/XXXX_add_validation_results_table.py` — migration for validation_results table

---

## Sources

### Primary (HIGH confidence)
- Live project code — `src/civpulse_geo/providers/base.py`, `census.py`, `services/geocoding.py`, `normalization.py`, `models/geocoding.py`, `api/geocoding.py`, `scripts/seed.py`, `pyproject.toml`
- Live scourgify execution — `normalize_address_record()` behavior verified with 8+ test inputs in project venv
- Live SHP binary inspection — `data/SAMPLE_Address_Points.shp.zip` parsed with Python stdlib `struct` + `zipfile` to discover EPSG:2240 CRS
- Live KML inspection — `data/SAMPLE_MBIT2017.DBO.AddressPoint.kml` parsed with stdlib `xml.etree.ElementTree`
- Live GeoJSON inspection — `data/SAMPLE_Address_Points.geojson` field names verified directly
- Live test run — 90 tests pass in 0.47s confirming baseline

### Secondary (MEDIUM confidence)
- CONTEXT.md decisions from `/gsd:discuss-phase` — locked implementation choices, field mapping intent
- STATE.md accumulated context — Phase 1/2 lessons learned (Alembic autogenerate issue, scourgify exception class name)
- alembic/versions/b98c26825b02_initial_schema.py — exact constraint names (`uq_geocoding_address_provider`, `uq_validation_address_provider` pattern)

### Tertiary (LOW confidence, for validation)
- fiona KML driver availability — needs verification at install time (recommendation: use stdlib xml for KML to avoid dependency on GDAL KML driver enablement)

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — scourgify, fiona need verified in project venv; SHP CRS issue confirmed by direct binary inspection
- Architecture: HIGH — all patterns derived directly from existing passing code in the same project
- Pitfalls: HIGH — SHP CRS pitfall discovered empirically; Alembic autogenerate pitfall from STATE.md lesson; AdminOverride pitfall from code analysis

**Research date:** 2026-03-19
**Valid until:** 2026-06-19 (scourgify and fiona are stable libraries; SHP CRS discovery is a permanent project fact)
