# Phase 11: Fix Batch Endpoint Local Provider Serialization - Research

**Researched:** 2026-03-24
**Domain:** FastAPI batch endpoint serialization / local provider result wiring
**Confidence:** HIGH

---

## Summary

GAP-INT-01, identified in the v1.1 milestone audit, described a defect where `POST /geocode/batch`
and `POST /validate/batch` silently dropped local provider results (`local_results` /
`local_candidates`). The service layer (Phase 7 pipeline) correctly returned local results; the
failure was in the batch API handler serialization functions `_geocode_one()` and `_validate_one()`,
which constructed their `GeocodeResponse` / `ValidateResponse` objects without passing the
`local_results=` and `local_candidates=` keyword arguments.

**Critical finding: The fix was already applied in commit f6f904d** ("fix(batch-api): wire local
provider results through batch serialization (GAP-INT-01)") before this planning phase was
initiated. Both `_geocode_one()` and `_validate_one()` now correctly build and pass local result
lists. Two regression tests (`test_batch_geocode_local_results_included`,
`test_batch_validate_local_candidates_included`) were added in the same commit and both pass.

**Implication for planning:** Phase 11 has zero implementation work remaining. The single plan
(`11-01-PLAN.md`) must acknowledge the pre-applied fix, document what was changed, verify all
tests pass, and close the gap formally via documentation — not by writing any new code.

**Primary recommendation:** Plan 11-01 is a verification/documentation task, not an
implementation task. The executor should run the test suite, confirm 16/16 batch tests pass
(including the two new regression tests), update ROADMAP.md Phase 11 checkbox, and write the
VERIFICATION.md / SUMMARY.md to close GAP-INT-01.

---

## Standard Stack

No new libraries introduced in this phase.

| Layer | File | Role |
|-------|------|------|
| API handler | `src/civpulse_geo/api/geocoding.py` | `_geocode_one()` batch helper — FIXED |
| API handler | `src/civpulse_geo/api/validation.py` | `_validate_one()` batch helper — FIXED |
| Schema (Pydantic) | `src/civpulse_geo/schemas/geocoding.py` | `GeocodeResponse.local_results` field |
| Schema (Pydantic) | `src/civpulse_geo/schemas/validation.py` | `ValidateResponse.local_candidates` field |
| Provider schema | `src/civpulse_geo/providers/schemas.py` | `GeocodingResult` / `ValidationResult` dataclasses |
| Tests | `tests/test_batch_geocoding_api.py` | Regression test added |
| Tests | `tests/test_batch_validation_api.py` | Regression test added |

**Test runner:** `uv run pytest` (project uses uv, no plain `python`/`python3` in PATH)

---

## Architecture Patterns

### How Single-Address Endpoints Work (Reference)

`POST /geocode` (lines 39-101 of `api/geocoding.py`) calls `GeocodingService.geocode()`, which
returns a dict with keys `results` (list of ORM rows) and `local_results` (list of
`GeocodingResult` dataclass instances). The single-address handler builds two separate lists:

```python
# ORM rows use .latitude/.longitude
provider_results = [GeocodeProviderResult(latitude=r.latitude, ...) for r in result["results"]]

# Dataclass instances use .lat/.lng (different field names)
local_provider_results = [GeocodeProviderResult(latitude=r.lat, longitude=r.lng, ...) for r in result.get("local_results", [])]

return GeocodeResponse(..., results=provider_results, local_results=local_provider_results, ...)
```

**The key field-name asymmetry:** ORM rows have `.latitude`/`.longitude`; provider dataclasses
(`GeocodingResult` from `providers/schemas.py`) have `.lat`/`.lng`. This distinction must be
preserved in both the single and batch paths.

### What Was Missing Before the Fix

Before commit f6f904d, `_geocode_one()` in `api/geocoding.py` (previously around line 255)
constructed `GeocodeResponse` without `local_results=`:

```python
# BEFORE (broken):
data = GeocodeResponse(
    address_hash=result["address_hash"],
    normalized_address=result["normalized_address"],
    cache_hit=result["cache_hit"],
    results=provider_results,
    # local_results= missing — defaulted to []
    official=official,
)
```

Similarly, `_validate_one()` (previously around line 133) constructed `ValidateResponse` without
`local_candidates=`.

### What Was Applied in the Fix (f6f904d)

The commit added to `_geocode_one()`:

```python
local_provider_results = [
    GeocodeProviderResult(
        provider_name=r.provider_name,
        latitude=r.lat,       # dataclass uses .lat, not .latitude
        longitude=r.lng,      # dataclass uses .lng, not .longitude
        location_type=r.location_type,
        confidence=r.confidence,
    )
    for r in result.get("local_results", [])
]
# ... then passed as:
data = GeocodeResponse(..., local_results=local_provider_results, ...)
```

And added to `_validate_one()`:

```python
local_candidates = [
    ValidationCandidate(
        normalized_address=c.normalized_address or "",
        address_line_1=c.address_line_1,
        address_line_2=c.address_line_2,
        city=c.city,
        state=c.state,
        postal_code=c.postal_code,
        confidence=c.confidence or 0.0,
        delivery_point_verified=c.delivery_point_verified,
        provider_name=c.provider_name,
    )
    for c in result.get("local_candidates", [])
]
# ... then passed as:
data = ValidateResponse(..., local_candidates=local_candidates, ...)
```

### Schema Definitions (Confirmed Current)

`GeocodeResponse` in `schemas/geocoding.py`:
```python
class GeocodeResponse(BaseModel):
    address_hash: str
    normalized_address: str
    cache_hit: bool
    results: list[GeocodeProviderResult]
    local_results: list[GeocodeProviderResult] = []   # default [] — already existed
    official: GeocodeProviderResult | None = None
```

`ValidateResponse` in `schemas/validation.py`:
```python
class ValidateResponse(BaseModel):
    address_hash: str
    original_input: str
    candidates: list[ValidationCandidate]
    local_candidates: list[ValidationCandidate] = []  # default [] — already existed
    cache_hit: bool
```

Both schema fields existed before the fix; the omission was only in the batch handlers not
passing populated lists.

---

## Don't Hand-Roll

| Problem | Don't Build | Reason |
|---------|-------------|--------|
| Field mapping between ORM rows and dataclasses | A custom adapter class | Simple dict comprehensions are the established pattern throughout the codebase |
| Regression detection | Manual inspection | Tests already cover the gap; just run them |

---

## Common Pitfalls

### Pitfall 1: Field Name Confusion (.lat/.lng vs .latitude/.longitude)

**What goes wrong:** A developer copying the ORM row mapping pattern uses `r.latitude`/`r.longitude`
for local provider results, which are `GeocodingResult` dataclasses with `.lat`/`.lng` fields.
This would produce `AttributeError` at runtime.

**Why it happens:** The project has two result types: ORM rows (cached DB results with
`.latitude`/`.longitude`) and `GeocodingResult` dataclasses (live local provider results with
`.lat`/`.lng`). The field names differ intentionally.

**How to avoid:** Always verify which object type is being iterated. ORM results come from
`result["results"]`; dataclass results come from `result.get("local_results", [])`.

**Warning signs:** `AttributeError: 'GeocodingResult' object has no attribute 'latitude'`

### Pitfall 2: Assuming the Fix Is Still Needed

**What goes wrong:** A planner/executor writes implementation steps to add `local_results=`
wiring as if it hasn't been done yet, and the executor produces a no-op diff or a "nothing
to change" message mid-plan.

**Why it happens:** The gap was identified in the audit but the fix was committed before the
planning phase ran.

**How to avoid:** Verify file state from git before writing implementation steps. The plan
for Phase 11 should be verification-first, not implementation-first.

### Pitfall 3: Pre-existing test_import_cli.py Failures

**What goes wrong:** Running the full test suite shows 10 failures and a developer marks
Phase 11 as blocked.

**Why it happens:** `tests/test_import_cli.py` has 10 pre-existing failures due to a missing
`data/SAMPLE_Address_Points.geojson` fixture. This predates v1.1 and is documented in the
milestone audit tech_debt section.

**How to avoid:** Run batch-specific tests only for Phase 11 verification:
`uv run pytest tests/test_batch_geocoding_api.py tests/test_batch_validation_api.py -v`
Full suite: expect 325 passed, 10 failed (pre-existing), 2 skipped.

---

## Code Examples

### Current State of _geocode_one() (api/geocoding.py, lines 219-290)

The function signature and full flow, post-fix:

```python
async def _geocode_one(
    index: int,
    freeform: str,
    semaphore: asyncio.Semaphore,
    service: GeocodingService,
    db: AsyncSession,
    providers: dict,
    http_client,
) -> BatchGeocodeResultItem:
    try:
        async with semaphore:
            result = await service.geocode(freeform=freeform, db=db, providers=providers, http_client=http_client)
        provider_results = [
            GeocodeProviderResult(provider_name=r.provider_name, latitude=r.latitude,
                                  longitude=r.longitude, location_type=r.location_type.value if r.location_type else None,
                                  confidence=r.confidence)
            for r in result["results"]
        ]
        local_provider_results = [
            GeocodeProviderResult(provider_name=r.provider_name, latitude=r.lat, longitude=r.lng,
                                  location_type=r.location_type, confidence=r.confidence)
            for r in result.get("local_results", [])
        ]
        official = None
        if result.get("official"):
            o = result["official"]
            official = GeocodeProviderResult(...)
        data = GeocodeResponse(
            address_hash=result["address_hash"],
            normalized_address=result["normalized_address"],
            cache_hit=result["cache_hit"],
            results=provider_results,
            local_results=local_provider_results,   # <-- GAP-INT-01 fix
            official=official,
        )
        return BatchGeocodeResultItem(index=index, original_input=freeform,
                                      status_code=200, status="success", data=data, error=None)
    except Exception as exc:
        ...
```

### Regression Test Pattern (test_batch_geocoding_api.py, lines 263-314)

```python
def _make_geocode_success_return_with_local(...):
    from civpulse_geo.providers.schemas import GeocodingResult
    local = GeocodingResult(lat=32.84, lng=-83.63, location_type="ROOFTOP",
                            confidence=0.95, raw_response={}, provider_name="test-local")
    return {"address_hash": address_hash, ..., "local_results": [local], "official": None}

@pytest.mark.asyncio
async def test_batch_geocode_local_results_included(patched_app_state):
    with patch("civpulse_geo.services.geocoding.GeocodingService.geocode",
               new_callable=AsyncMock, return_value=_make_geocode_success_return_with_local()):
        response = await client.post("/geocode/batch", json={"addresses": ["123 Main St..."]})
    item = response.json()["results"][0]
    assert len(item["data"]["local_results"]) == 1
    assert item["data"]["local_results"][0]["provider_name"] == "test-local"
```

---

## State of the Art

| Old State (pre-f6f904d) | Current State (post-f6f904d) | Impact |
|------------------------|------------------------------|--------|
| `_geocode_one()` omitted `local_results=` — defaulted to `[]` | `local_results=local_provider_results` passed | Batch callers now receive local provider geocoding results |
| `_validate_one()` omitted `local_candidates=` — defaulted to `[]` | `local_candidates=local_candidates` passed | Batch callers now receive local provider validation candidates |
| No regression tests for batch local results | 2 regression tests added (one per endpoint) | Future regressions will be caught automatically |

---

## Open Questions

1. **Does Phase 11 need a formal VALIDATION.md / SUMMARY.md?**
   - What we know: `commit_docs: true` in config.json; the GSD workflow requires VALIDATION.md
     and SUMMARY.md for each phase.
   - What's unclear: Whether a verification-only phase with no new implementation warrants
     full Nyquist validation documentation.
   - Recommendation: Yes — follow the standard pattern. SUMMARY.md documents what f6f904d
     changed; VALIDATION.md documents the test evidence confirming GAP-INT-01 is closed.

2. **Should the roadmap Phase 11 checkbox be marked complete as part of this plan?**
   - What we know: ROADMAP.md shows `- [ ] **Phase 11: ...**` and `- [ ] 11-01-PLAN.md`
     as unchecked. The code fix is done but the planning/verification documentation is not.
   - Recommendation: Yes — the 11-01-PLAN.md executor should update both checkboxes as part
     of the phase close.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (via uv) |
| Config file | pyproject.toml (`[tool.pytest.ini_options]`) |
| Quick run command | `uv run pytest tests/test_batch_geocoding_api.py tests/test_batch_validation_api.py -v` |
| Full suite command | `uv run pytest --no-header -q` |

### Phase Requirements → Test Map

This phase has no stated v1.1 requirement IDs. It closes GAP-INT-01.

| Gap ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| GAP-INT-01 (geocode) | `POST /geocode/batch` includes `local_results` in each response item | unit/integration | `uv run pytest tests/test_batch_geocoding_api.py::test_batch_geocode_local_results_included -v` | Yes |
| GAP-INT-01 (validate) | `POST /validate/batch` includes `local_candidates` in each response item | unit/integration | `uv run pytest tests/test_batch_validation_api.py::test_batch_validate_local_candidates_included -v` | Yes |

### Sampling Rate

- **Per task commit:** `uv run pytest tests/test_batch_geocoding_api.py tests/test_batch_validation_api.py -v`
- **Per wave merge:** `uv run pytest --no-header -q` (expect: 325 passed, 10 pre-existing failures, 2 skipped)
- **Phase gate:** Both regression tests green before `/gsd:verify-work`

### Wave 0 Gaps

None — all test infrastructure exists. Both regression tests were added in commit f6f904d and
currently pass.

---

## Sources

### Primary (HIGH confidence)

- Direct source read: `src/civpulse_geo/api/geocoding.py` — full `_geocode_one()` implementation confirmed
- Direct source read: `src/civpulse_geo/api/validation.py` — full `_validate_one()` implementation confirmed
- `git show f6f904d` — exact diff of what the fix applied, verified against current file state
- Direct source read: `src/civpulse_geo/schemas/geocoding.py` — `GeocodeResponse` schema, `local_results` field
- Direct source read: `src/civpulse_geo/schemas/validation.py` — `ValidateResponse` schema, `local_candidates` field
- Direct source read: `src/civpulse_geo/providers/schemas.py` — `GeocodingResult` dataclass field names (`.lat`/`.lng`)
- Test execution: `uv run pytest tests/test_batch_geocoding_api.py tests/test_batch_validation_api.py` — 16/16 passed
- `.planning/v1.1-MILESTONE-AUDIT.md` — authoritative gap description with line numbers and root cause

### Secondary (MEDIUM confidence)

- `.planning/ROADMAP.md` — Phase 11 description and plan list
- `.planning/STATE.md` — project history and accumulated decisions

---

## Metadata

**Confidence breakdown:**
- Current code state: HIGH — directly verified via file read and git diff
- Test coverage: HIGH — executed and confirmed 16/16 pass
- Gap closure status: HIGH — commit f6f904d applied the fix before this research ran; nothing remains to implement
- Plan shape: HIGH — verification + documentation only, no new code

**Research date:** 2026-03-24
**Valid until:** N/A — this is a point-in-time code audit, not ecosystem research
