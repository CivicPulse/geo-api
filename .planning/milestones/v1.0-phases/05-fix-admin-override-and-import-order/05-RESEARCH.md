# Phase 5: Fix Admin Override & Import Order - Research

**Researched:** 2026-03-19
**Domain:** SQLAlchemy async upsert, PostgreSQL ON CONFLICT, CLI sync psycopg2, cross-layer integration testing
**Confidence:** HIGH

## Summary

This is a gap-closure phase with two distinct requirements. GEO-07 has a silent bug: `GeocodingService.set_official()` correctly creates a `GeocodingResult` with `provider_name="admin_override"` and upserts `OfficialGeocoding`, but never writes a row to the `admin_overrides` table. The `AdminOverride` ORM model is fully defined and exported — it just needs to be populated in the `else` branch of `set_official()` (lines 287–343 of `geocoding.py`). The fix is a single additional `pg_insert(AdminOverride).on_conflict_do_update(...)` call after the existing `GeocodingResult` upsert.

DATA-03 is an operational constraint, not a code defect. The CLI uses `ON CONFLICT (address_id) DO NOTHING` when auto-setting `official_geocoding`, which means the first source to write wins. If an address is geocoded via the API before GIS import, census remains official. DATA-03 compliance therefore requires GIS import to precede API geocoding — this is documented as a deployment constraint, not fixed in code (confirmed by user in prior exploration). The existing CLI admin-override guard that reads `admin_overrides` becomes functionally correct once GEO-07 is fixed.

The phase requires: one code change in `geocoding.py`, new unit tests covering the `admin_overrides` write and the fixed CLI guard, cross-phase integration tests, and documentation of the import-order operational constraint. No schema migrations are needed — the `admin_overrides` table already exists.

**Primary recommendation:** Fix `set_official()` to upsert `AdminOverride` alongside the existing `GeocodingResult` upsert; document the GIS-first import constraint in CLI docstrings and operational runbooks.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| GEO-07 | Admin can set a custom lat/lng coordinate as the official location (not from any provider) | `AdminOverride` ORM fully defined in `models/geocoding.py` lines 66–87; `pg_insert` pattern already used in `set_official()`; fix is adding one upsert call in the `else` branch |
| DATA-03 | When county GIS data exists for an address and no admin override is set, the county data is used as the default official record | Operational constraint — fix is documentation, not code change; GIS import must run before API geocoding; CLI guard becomes correctly functional once GEO-07 fixes the `admin_overrides` write |
</phase_requirements>

---

## Standard Stack

### Core (already installed — no new dependencies)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| SQLAlchemy (async) | project-current | `pg_insert(AdminOverride).on_conflict_do_update(...)` | All async DB writes already use this pattern |
| `sqlalchemy.dialects.postgresql.insert` | project-current | `pg_insert` alias already imported in `geocoding.py` line 21 | Already in the file |
| pytest-asyncio | project-current | Async unit tests for `set_official()` | All service tests already use `@pytest.mark.asyncio` |
| typer.testing.CliRunner | project-current | CLI import guard regression test | All CLI tests already use this |

**No new packages required.** This phase touches only existing code.

---

## Architecture Patterns

### Recommended Project Structure

No structural changes. Touches existing files:

```
src/civpulse_geo/services/geocoding.py    # +8 lines in set_official() else-branch
tests/test_geocoding_service.py           # +new test: admin_override writes to admin_overrides
tests/test_import_cli.py                  # +new test: CLI guard correctly skips with admin_override row
tests/test_geocoding_api.py               # (optional) API-level regression for custom coord path
```

### Pattern 1: AdminOverride Upsert (the fix)

**What:** After upserting the `GeocodingResult` and before the `OfficialGeocoding` upsert, insert/update a row in `admin_overrides`. Mirrors the existing `pg_insert(OfficialGeocoding)` pattern.

**When to use:** Only in the `else` branch of `set_official()` — the custom lat/lng path.

**Exact insertion point:** After line 318 (`result_id = upsert_result.scalar_one()`) and before line 321 (the re-query).

**Example:**
```python
# Source: existing pg_insert pattern in geocoding.py lines 270–280
await db.execute(
    pg_insert(AdminOverride)
    .values(
        address_id=address.id,
        location=ewkt_point,
        latitude=latitude,
        longitude=longitude,
        reason=reason,
    )
    .on_conflict_do_update(
        index_elements=["address_id"],
        set_={
            "location": ewkt_point,
            "latitude": latitude,
            "longitude": longitude,
            "reason": reason,
        },
    )
)
```

**Import addition required in geocoding.py:**
```python
from civpulse_geo.models.geocoding import (
    GeocodingResult as GeocodingResultORM,
    OfficialGeocoding,
    AdminOverride,        # ADD THIS
)
```

**Verify current imports:** Check whether `AdminOverride` is already imported in `geocoding.py` before adding it.

### Pattern 2: CLI Guard — Already Correct After Fix

**What:** `cli/__init__.py` lines 186–189 run:
```python
override_row = conn.execute(
    text("SELECT id FROM admin_overrides WHERE address_id = :aid"),
    {"aid": address_id},
).fetchone()
```

Once GEO-07 writes to `admin_overrides`, this guard correctly returns a row for admin-overridden addresses, and `ON CONFLICT DO NOTHING` preserves them. **No change needed in the CLI.**

### Pattern 3: DATA-03 Documentation

**What:** Add inline comments and a docstring note in `cli/__init__.py` explaining the import-order constraint.

**Where:**
1. At the `ON CONFLICT DO NOTHING` SQL statement (lines 193–200) — inline comment explaining why first-writer-wins is intentional
2. At the top of `import_gis()` function docstring — operational note

**Example comment text:**
```python
# DATA-03 operational constraint: GIS data MUST be imported before the API
# geocodes addresses. This INSERT uses ON CONFLICT DO NOTHING so that any
# existing official record is preserved. If census geocoding runs first,
# county GIS will not displace it. Use the PUT /geocode/{hash}/official
# endpoint to correct the record when ordering is violated.
```

### Anti-Patterns to Avoid

- **Changing `ON CONFLICT DO NOTHING` to `DO UPDATE` for DATA-03:** The audit audit identified this as an option, but the user confirmed DO NOTHING is correct behavior. Do NOT change it.
- **Duplicating the `AdminOverride` write in the provider-result path:** Only the custom lat/lng `else` branch writes to `admin_overrides`. Setting official to a provider result does NOT create an admin override row.
- **Separate commit for AdminOverride:** The `admin_overrides` upsert must happen within the same `db.execute`/`db.commit()` block as the `GeocodingResult` and `OfficialGeocoding` upserts. There is only one `await db.commit()` at line 338.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Upsert with update-on-conflict | Custom SELECT + UPDATE logic | `pg_insert(...).on_conflict_do_update(index_elements=["address_id"], set_={...})` | Already the pattern for GeocodingResult and OfficialGeocoding in the same function |
| Mock DB execute sequence in tests | Custom test DB fixtures | `AsyncMock(side_effect=[...])` sequence | Already established in `test_geocoding_service.py` for all set_official tests |

**Key insight:** The `pg_insert` pattern is battle-tested across this codebase. The fix is literally copy/paste of the OfficialGeocoding upsert pattern, adjusted for the AdminOverride model columns.

---

## Common Pitfalls

### Pitfall 1: AdminOverride Not Imported in geocoding.py

**What goes wrong:** `NameError: name 'AdminOverride' is not defined` at runtime.

**Why it happens:** `geocoding.py` imports `GeocodingResult as GeocodingResultORM` and `OfficialGeocoding` but may not import `AdminOverride`. Check the current import block before writing the fix.

**How to avoid:** Verify imports at lines 1–30 of `geocoding.py` before writing the fix.

**Warning signs:** `NameError` or `ImportError` in tests.

### Pitfall 2: Mock Sequence Mismatch in Tests

**What goes wrong:** Existing `test_set_custom_official` and `test_set_custom_official_stores_reason` tests fail because they mock 4 `db.execute` calls, but the fix adds a 5th (the `AdminOverride` upsert).

**Why it happens:** `AsyncMock(side_effect=[...])` raises `StopIteration` (surfaced as `StopAsyncIteration`) if the list is exhausted.

**How to avoid:** Update the existing `test_set_custom_official` and `test_set_custom_official_stores_reason` tests to add a 5th mock result in their `side_effect` list. Insert it after the `GeocodingResult` upsert result and before the OfficialGeocoding upsert result.

**Execute call order after fix:**
1. Address lookup (`scalars().first()` → Address)
2. GeocodingResult upsert (`.returning()` → `scalar_one()` → result_id)
3. AdminOverride upsert (NEW — just `MagicMock()`)
4. GeocodingResult re-query (`scalars().first()` → new_gr)
5. OfficialGeocoding upsert (`MagicMock()`)

**Warning signs:** `StopAsyncIteration` or unexplained test failure in `test_set_custom_official`.

### Pitfall 3: AdminOverride `location` Column is NOT NULL

**What goes wrong:** DB-level `NOT NULL` constraint violation if `ewkt_point` is incorrect or omitted.

**Why it happens:** `AdminOverride.location` is `nullable=False` (line 76 of `models/geocoding.py`). The `GeocodingResult` location column is `nullable=True` — different constraint.

**How to avoid:** Use the same `ewkt_point = f"SRID=4326;POINT({longitude} {latitude})"` string already computed at line 289.

**Warning signs:** `IntegrityError: null value in column "location"` in integration tests.

### Pitfall 4: AdminOverride `reason` Column Is TEXT, Nullable

**What goes wrong:** Passing an empty string instead of `None` for missing reason.

**Why it happens:** The `reason` parameter defaults to `None` in `set_official()`. The column is `nullable=True` (line 83). Either `None` or a non-empty string is valid.

**How to avoid:** Pass `reason=reason` directly — `None` is valid for the column.

### Pitfall 5: Confusing set_official GEO-06 Path with GEO-07 Path

**What goes wrong:** Adding AdminOverride upsert to the `if has_result_id:` branch (GEO-06 — setting to a provider result), which is wrong. GEO-06 sets official to an existing provider result; no admin override row should be created.

**Why it happens:** The two branches share structure.

**How to avoid:** The AdminOverride write belongs ONLY in the `else:` branch (line 287 onward). Do not modify the `if has_result_id:` branch.

---

## Code Examples

Verified from project source files:

### Existing pg_insert Pattern (OfficialGeocoding upsert)
```python
# Source: src/civpulse_geo/services/geocoding.py lines 327–337
await db.execute(
    pg_insert(OfficialGeocoding)
    .values(
        address_id=address.id,
        geocoding_result_id=result_id,
    )
    .on_conflict_do_update(
        index_elements=["address_id"],
        set_={"geocoding_result_id": result_id},
    )
)
```

### AdminOverride ORM Model Columns (source of truth for upsert values)
```python
# Source: src/civpulse_geo/models/geocoding.py lines 66–87
class AdminOverride(Base, TimestampMixin):
    __tablename__ = "admin_overrides"
    id: Mapped[int] = mapped_column(primary_key=True)
    address_id: Mapped[int] = mapped_column(ForeignKey("addresses.id"), unique=True)
    location: Mapped[object] = mapped_column(Geography(...), nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
```

### CLI Admin Override Guard (currently broken, fixed by GEO-07)
```python
# Source: src/civpulse_geo/cli/__init__.py lines 186–200
override_row = conn.execute(
    text("SELECT id FROM admin_overrides WHERE address_id = :aid"),
    {"aid": address_id},
).fetchone()

if override_row is None:
    conn.execute(
        text("""
            INSERT INTO official_geocoding (address_id, geocoding_result_id)
            VALUES (:address_id, :geocoding_result_id)
            ON CONFLICT (address_id) DO NOTHING
        """),
        {"address_id": address_id, "geocoding_result_id": geocoding_result_id},
    )
```

### Test Mock Sequence Pattern for set_official Custom Path (current — 4 calls)
```python
# Source: tests/test_geocoding_service.py lines 635–649
db.execute = AsyncMock(side_effect=[
    addr_result,       # 1: address lookup
    upsert_gr_result,  # 2: GeocodingResult upsert (.scalar_one())
    requery_result,    # 3: re-query new GeocodingResult row
    official_upsert,   # 4: OfficialGeocoding upsert
])
```

After the fix, this becomes 5 calls (AdminOverride upsert inserted as call 3, pushing re-query to 4 and OfficialGeocoding to 5).

---

## State of the Art

| Old Approach | Current Approach | Notes |
|--------------|------------------|-------|
| `ON CONFLICT DO NOTHING` for AdminOverride | `ON CONFLICT DO UPDATE` for AdminOverride | Fix: admin re-setting same address should UPDATE lat/lng/reason, not silently do nothing |

**Key distinction:** `OfficialGeocoding` uses `DO UPDATE` (always points to latest winner). `AdminOverride` should also use `DO UPDATE` — if admin calls `set_official` twice for the same address, the second call should update the override, not silently no-op.

---

## Open Questions

1. **AdminOverride import in geocoding.py**
   - What we know: `AdminOverride` is exported from `models/__init__.py` line 4
   - What's unclear: Whether it is currently imported in `services/geocoding.py` import block
   - Recommendation: Check lines 1–30 of `geocoding.py` immediately; if not imported, add to the existing `from civpulse_geo.models.geocoding import ...` line

2. **DATA-03 — exactly where to add documentation**
   - What we know: CLI ON CONFLICT DO NOTHING is at `cli/__init__.py` lines 193–200; user confirmed this is correct
   - What's unclear: Whether the operational constraint also needs a note in the API's `set_official` docstring or only in the CLI
   - Recommendation: Document in both the CLI inline comment and the CLI function docstring; the API docstring is lower priority since the constraint is about import order, not the API call itself

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio |
| Config file | `pyproject.toml` (project-current) |
| Quick run command | `pytest tests/test_geocoding_service.py -x -q` |
| Full suite command | `pytest tests/ -x -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| GEO-07 | set_official custom path writes row to admin_overrides | unit | `pytest tests/test_geocoding_service.py::test_set_custom_official_writes_admin_overrides -x` | Wave 0 |
| GEO-07 | set_official custom path upserts (updates on second call) | unit | `pytest tests/test_geocoding_service.py::test_set_custom_official_upserts_on_second_call -x` | Wave 0 |
| GEO-07 | Existing test_set_custom_official still passes with 5-call mock | unit (regression) | `pytest tests/test_geocoding_service.py::test_set_custom_official -x` | Exists (needs update) |
| GEO-07 | Existing test_set_custom_official_stores_reason still passes | unit (regression) | `pytest tests/test_geocoding_service.py::test_set_custom_official_stores_reason -x` | Exists (needs update) |
| DATA-03 | CLI guard skips official-set when admin_overrides row exists | unit | `pytest tests/test_import_cli.py::TestImportGISCommand::test_import_skips_official_when_admin_override_exists -x` | Wave 0 |
| DATA-03 | Import-order constraint documented in CLI docstring | manual | inspect `cli/__init__.py` docstring | N/A |

### Sampling Rate

- **Per task commit:** `pytest tests/test_geocoding_service.py -x -q`
- **Per wave merge:** `pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/test_geocoding_service.py` — add `test_set_custom_official_writes_admin_overrides` test
- [ ] `tests/test_geocoding_service.py` — add `test_set_custom_official_upserts_on_second_call` test
- [ ] `tests/test_geocoding_service.py` — update existing `test_set_custom_official` and `test_set_custom_official_stores_reason` to 5-call mock sequence
- [ ] `tests/test_import_cli.py` — add `test_import_skips_official_when_admin_override_exists` test

---

## Sources

### Primary (HIGH confidence)

- Direct source read: `src/civpulse_geo/services/geocoding.py` — `set_official()` function, lines 205–343 (the exact bug location and fix target)
- Direct source read: `src/civpulse_geo/models/geocoding.py` — `AdminOverride` ORM model, lines 66–87 (column definitions, constraints)
- Direct source read: `src/civpulse_geo/cli/__init__.py` — guard and ON CONFLICT logic, lines 185–200
- Direct source read: `tests/test_geocoding_service.py` — existing mock patterns, lines 602–699 (custom path tests)
- `.planning/v1.0-MILESTONE-AUDIT.md` — root cause analysis for both gaps, confirmed fix strategies
- `.planning/ROADMAP.md` Phase 5 success criteria — explicit requirements for what "done" means

### Secondary (MEDIUM confidence)

- `.planning/STATE.md` decisions section — `[Phase 02 Plan 02]` entries confirm the GEO-07 design intent and ON CONFLICT DO NOTHING reasoning

---

## Metadata

**Confidence breakdown:**
- Bug location: HIGH — source code verified, exact lines identified
- Fix approach: HIGH — mirrors existing pg_insert pattern in same function
- Test impact: HIGH — existing test mock sequences identified, update count known (2 tests need +1 mock call)
- DATA-03 scope: HIGH — user confirmed "document only, no code change" in additional context
- AdminOverride import status: MEDIUM — `__init__.py` exports it but `geocoding.py` import block not fully verified

**Research date:** 2026-03-19
**Valid until:** Stable (no external dependencies; pure internal code change)
