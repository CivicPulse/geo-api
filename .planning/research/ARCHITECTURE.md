# Architecture Research

**Domain:** CivPulse Geo API — v1.2 Cascading Address Resolution
**Researched:** 2026-03-29
**Confidence:** HIGH — based on direct codebase inspection, verified PostGIS/pg_trgm official docs, and Ollama Docker documentation

---

## v1.2 Milestone: Cascading Address Resolution Pipeline

This section covers the architecture for the v1.2 milestone only. The v1.1 architecture (local data source providers) is preserved at the bottom of this file for reference.

---

### System Overview: v1.2 Cascade Pipeline

```
┌──────────────────────────────────────────────────────────────────────────┐
│  FastAPI Request Layer                                                     │
│  POST /geocode  ->  GeocodingService.geocode()                            │
└────────────────────────────┬─────────────────────────────────────────────┘
                             │
┌────────────────────────────▼─────────────────────────────────────────────┐
│  Stage 1 - Pre-processing (NEW)                                           │
│  ┌───────────────────┐    ┌────────────────────────────────────────────┐  │
│  │  SpellCorrector   │ -> │  scourgify / canonical_key()  [EXISTING]   │  │
│  │  (street tokens)  │    └────────────────────────────────────────────┘  │
│  └───────────────────┘                                                    │
│                             corrected raw input -> normalized + hash      │
└────────────────────────────┬─────────────────────────────────────────────┘
                             │
┌────────────────────────────▼─────────────────────────────────────────────┐
│  Stage 2 - Cache Check (EXISTING, unchanged)                              │
│  DB lookup by address_hash -> cache hit returns early                     │
└────────────────────────────┬─────────────────────────────────────────────┘
                             │ (cache miss)
┌────────────────────────────▼─────────────────────────────────────────────┐
│  Stage 3 - Exact Provider Dispatch (EXISTING, unchanged interface)        │
│  ┌──────────────────────────────────────────────────────────────────┐    │
│  │  Local providers (is_local=True) - direct return, no DB write    │    │
│  │  OA  |  Tiger  |  NAD  |  Macon-Bibb  ->  local_results[]       │    │
│  └──────────────────────────────────────────────────────────────────┘    │
│  ┌──────────────────────────────────────────────────────────────────┐    │
│  │  Remote providers (is_local=False) - cached to DB                │    │
│  │  Census Geocoder  ->  geocoding_results rows                     │    │
│  └──────────────────────────────────────────────────────────────────┘    │
└────────────────────────────┬─────────────────────────────────────────────┘
                             │ (all providers returned confidence=0.0)
┌────────────────────────────▼─────────────────────────────────────────────┐
│  Stage 4 - Fuzzy Fallback (NEW)                                           │
│  FuzzyMatcher: pg_trgm similarity() + fuzzystrmatch metaphone()          │
│  Queries openaddresses_points and nad_points directly via SQL.            │
│  NOT a GeocodingProvider subclass.                                        │
│  Returns GeocodingResult(confidence <= 0.8) or None.                     │
└────────────────────────────┬─────────────────────────────────────────────┘
                             │ (still no result)
┌────────────────────────────▼─────────────────────────────────────────────┐
│  Stage 5 - LLM Sidecar Correction (NEW, opt-in)                          │
│  LLMAddressCorrector: httpx POST -> Ollama container /api/generate       │
│  Returns corrected_address string via structured JSON.                    │
│  If corrected != original -> re-enter Stage 1 (max 1 re-attempt).        │
│  If CASCADE_LLM_ENABLED=false or Ollama unreachable -> skip silently.    │
└────────────────────────────┬─────────────────────────────────────────────┘
                             │
┌────────────────────────────▼─────────────────────────────────────────────┐
│  Stage 6 - Consensus Scoring (NEW)                                        │
│  ConsensusScorer: pairwise Haversine distance across all collected results│
│  (local + remote + fuzzy). Cluster by distance threshold (default 200m). │
│  Outputs: winner GeocodingResult, cluster_size, outlier flags.           │
└────────────────────────────┬─────────────────────────────────────────────┘
                             │
┌────────────────────────────▼─────────────────────────────────────────────┐
│  Stage 7 - OfficialGeocoding Auto-Set (EXISTING, logic changes)           │
│  Current: first-writer-wins ON CONFLICT DO NOTHING.                       │
│  v1.2 cascade path: ON CONFLICT DO UPDATE with consensus winner.         │
│  Admin overrides skip ConsensusScorer entirely (unchanged).               │
└──────────────────────────────────────────────────────────────────────────┘
```

---

### Component Responsibilities

| Component | New or Modified | Responsibility | Location |
|-----------|----------------|----------------|----------|
| `SpellCorrector` | NEW | Correct misspelled street tokens before scourgify | `civpulse_geo/correction/spell.py` |
| `FuzzyMatcher` | NEW | pg_trgm + Soundex/Metaphone SQL against staging tables | `civpulse_geo/correction/fuzzy.py` |
| `LLMAddressCorrector` | NEW | httpx client to Ollama sidecar; structured address correction | `civpulse_geo/correction/llm.py` |
| `ConsensusScorer` | NEW | Score and rank results from all providers by geographic agreement | `civpulse_geo/correction/consensus.py` |
| `CascadeOrchestrator` | NEW | Coordinates Stages 1-7; owns the cascade decision tree | `civpulse_geo/services/cascade.py` |
| `GeocodingService` | MODIFIED | Delegates to `CascadeOrchestrator` when `CASCADE_ENABLED=true` | `civpulse_geo/services/geocoding.py` |
| `OfficialGeocoding` auto-set | MODIFIED | Cascade path uses `ON CONFLICT DO UPDATE`; non-cascade path unchanged | `civpulse_geo/services/geocoding.py` |
| `docker-compose.yml` | MODIFIED | Add `ollama` service with volume; add `OLLAMA_BASE_URL` to api env | `docker-compose.yml` |
| All provider ABCs + implementations | UNCHANGED | Zero changes required to `providers/` package | `civpulse_geo/providers/` |

---

## Recommended Project Structure

```
src/civpulse_geo/
├── correction/              # NEW package - all v1.2 correction/scoring logic
│   ├── __init__.py
│   ├── spell.py             # SpellCorrector: symspellpy token correction
│   ├── fuzzy.py             # FuzzyMatcher: pg_trgm + fuzzystrmatch SQL
│   ├── llm.py               # LLMAddressCorrector: Ollama sidecar client
│   └── consensus.py         # ConsensusScorer: distance-based agreement
├── services/
│   ├── cascade.py           # NEW: CascadeOrchestrator
│   ├── geocoding.py         # MODIFIED: delegate to CascadeOrchestrator
│   └── validation.py        # unchanged
├── providers/               # unchanged - ABCs and all provider impls
│   ├── base.py
│   ├── census.py
│   ├── openaddresses.py
│   ├── tiger.py
│   ├── nad.py
│   └── macon_bibb.py
└── ...                      # all other modules unchanged
```

### Structure Rationale

- **correction/:** All new components live in a dedicated package. This prevents any changes to `providers/` (the stable plugin system). The correction layer sits above providers in the call stack, not inside them.
- **services/cascade.py:** Owns the cascade decision tree and keeps `GeocodingService` from growing into a monolith. `GeocodingService` is the existing public API; `CascadeOrchestrator` is the v1.2 implementation detail behind a feature flag.
- **providers/ is frozen:** The provider ABCs and all five provider implementations require zero changes. All new cascade logic operates on `GeocodingResult` schemas already produced by providers.

---

## Architectural Patterns

### Pattern 1: Spell Correction Runs Before scourgify

**What:** `SpellCorrector` runs on the raw freeform input string before `canonical_key()` calls `scourgify`. Its output feeds into the existing normalization pipeline unchanged.

**Why before scourgify:** scourgify relies on USPS token matching. A misspelled street name like `NORTHMINISTR` causes scourgify to either fail silently (triggering the plain-uppercase fallback) or produce a garbled normalization where the street name token is unrecognized. If spell correction runs after normalization, it operates on an already-corrupted token. The address hash is then wrong and will never match a cached or staged record. Correction before scourgify ensures scourgify sees valid tokens and produces a valid canonical key.

**When to use:** Always, on raw input. symspellpy dictionary lookups are O(1) after the dictionary is loaded at startup — the overhead is negligible on every request.

**Scope constraint:** Only correct tokens classified as `StreetName` by `usaddress.tag()`. House numbers, city names, state abbreviations, ZIP codes, and directionals must not be spell-corrected. The standard English word dictionary has no idea that `GA` is a valid token; it would "correct" it to some English word.

**Error handling:** If `usaddress.tag()` raises `RepeatedLabelError` (ambiguous parse), skip spell correction entirely and pass the raw input to `canonical_key()`. Never allow a spell correction failure to block the pipeline.

**Trade-offs:** symspellpy requires a pre-loaded word frequency dictionary (~10 MB RAM). The bundled English dictionary (`frequency_dictionary_en_82765.txt`) covers common street name misspellings. A custom USPS street-name dictionary would improve precision for address-specific tokens but is a v2 consideration.

### Pattern 2: FuzzyMatcher as a Service-Layer Component, Not a Provider

**What:** `FuzzyMatcher` issues SQL directly against the local staging tables using `pg_trgm similarity()` and `fuzzystrmatch metaphone()`. It is NOT a `GeocodingProvider` subclass and is not registered in `app.state.providers`.

**Why not a provider:** Fuzzy matching is a query strategy fallback on existing data, not an independent data source. Implementing it as a provider would mean it runs on every request (alongside exact providers), not just as a cascade fallback. It also cannot be cleanly ordered after exact providers using the current provider dispatch loop. The correct boundary is the service layer: `CascadeOrchestrator` calls `FuzzyMatcher` explicitly and only after all exact providers return `confidence == 0.0`.

**pg_trgm vs Soundex/Metaphone:**

`pg_trgm similarity()` handles character-level typos and transpositions. Use it as the primary fuzzy strategy with a threshold of 0.6:
```sql
SELECT lat, lng, street, city, accuracy
FROM openaddresses_points
WHERE number = :house_number
  AND similarity(street, :street_name) > 0.6
ORDER BY similarity(street, :street_name) DESC
LIMIT 1
```

`metaphone()` from `fuzzystrmatch` handles phonetic variations (e.g., `CALHOUN` vs `COLHOON`). Use it as a secondary strategy when pg_trgm finds no match:
```sql
SELECT lat, lng, street, city
FROM openaddresses_points
WHERE number = :house_number
  AND metaphone(street, 10) = metaphone(:street_name, 10)
LIMIT 1
```

`fuzzystrmatch` is already enabled as a Tiger prerequisite — it requires no new DB setup. `pg_trgm` is NOT currently enabled and requires both `CREATE EXTENSION pg_trgm` and GIN trigram indexes on the street columns.

**Required schema changes:**

A new Alembic migration must:
1. `CREATE EXTENSION IF NOT EXISTS pg_trgm;`
2. `CREATE INDEX idx_oa_street_trgm ON openaddresses_points USING gin(street gin_trgm_ops);`
3. `CREATE INDEX idx_nad_street_trgm ON nad_points USING gin(street_name gin_trgm_ops);`

These are schema changes that belong in Alembic, not in the Tiger setup script.

**Confidence assignment:** Fuzzy match confidence = `similarity_score * 0.8`, capped at 0.8. This ensures fuzzy results rank below exact matches in `ConsensusScorer`.

**Query table order:** Query `openaddresses_points` first (densest for Macon-Bibb county). Fall back to `nad_points`. Tiger fuzzy tolerance is handled by the built-in Tiger geocoder rating system — do not implement a separate Tiger fuzzy query.

### Pattern 3: LLM Sidecar as Async HTTP Client with Graceful Degradation

**What:** `LLMAddressCorrector` is a thin async httpx client calling the Ollama container's REST API. It lives in `correction/llm.py` and is called only by `CascadeOrchestrator` as the last fallback when both spell correction and fuzzy matching fail.

**When to use:** Only when `CASCADE_LLM_ENABLED=true` (env var, default `false`) AND fuzzy matching returned no result.

**Integration with existing `app.state.http_client`:** Reuse the existing `httpx.AsyncClient` from `app.state.http_client`. Do not create a second client instance. The Ollama base URL is injected via `OLLAMA_BASE_URL` env var (default: `http://ollama:11434`).

**Prompt and structured output:**
```python
prompt = (
    f"Correct this US address. Return JSON only, no other text.\n"
    f"Input: {raw_address}\n"
    f'Output format: {{"corrected": "<corrected address>", "changed": true/false}}'
)
# POST to /api/generate with "stream": false, "format": "json"
```

**Re-entry rule:** If LLM returns `changed: true`, `CascadeOrchestrator` re-enters at Stage 1 with the corrected string. Maximum one LLM re-attempt — never loop. If the second pass still fails, return the best accumulated result (which may have `confidence == 0.0`).

**Timeout and failure handling:**
- Hard 10-second timeout on the httpx call.
- On `httpx.ConnectError` (Ollama not running): return `None`, log `WARNING`.
- On timeout: return `None`, log `WARNING`.
- Never let LLM latency block the geocoding response.

**Model selection:** `qwen2.5:1.5b` for CPU-only (fastest small instruction-tuned model, ~900 MB download). `llama3.2:3b` for GPU deployments. Configurable via `OLLAMA_MODEL` env var.

**Trade-offs:** The LLM sidecar is the highest-latency component in the cascade (1-5 seconds on CPU). The feature flag default of `false` ensures existing deployments are unaffected. The Ollama container must be started and the model pulled manually — the API container does not manage this.

### Pattern 4: Consensus Scoring on GeocodingResult Schemas

**What:** `ConsensusScorer` accepts a `list[GeocodingResult]` (the provider schema dataclasses, not ORM rows) and uses pairwise Haversine distance to identify clusters of agreement. It selects the winning result and flags outliers.

**Algorithm:**
1. Discard results with `confidence == 0.0`.
2. Compute pairwise Haversine distances between all remaining results.
3. Group results where pairwise distance <= `CONSENSUS_DISTANCE_THRESHOLD_METERS` (default 200m, configurable via env var `CONSENSUS_DISTANCE_M`).
4. Pick the largest cluster. On tie, prefer the cluster containing the highest-confidence result.
5. Within the winning cluster, the result with the highest `confidence` is the winner.
6. `consensus_confidence = winner.confidence * (cluster_size / total_results)`

**Implementation with stdlib math only:**
```python
import math

def haversine_meters(lat1, lng1, lat2, lng2) -> float:
    R = 6_371_000  # Earth radius in meters
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return 2 * R * math.asin(math.sqrt(a))
```

No additional library is required. The `haversine` PyPI package is not needed.

**Integration with OfficialGeocoding:** `ConsensusScorer` outputs a `ConsensusResult` dataclass. `CascadeOrchestrator` passes the winner's `GeocodingResult` to a new `GeocodingService._set_official_from_cascade()` method that uses `ON CONFLICT DO UPDATE SET geocoding_result_id = EXCLUDED.geocoding_result_id`. This replaces the existing `ON CONFLICT DO NOTHING` behavior for the cascade path only. The non-cascade path (direct `GeocodingService.geocode()` call without cascade enabled) retains `DO NOTHING`.

**Admin override immunity:** `provider_name == "admin_override"` results are never included in the `ConsensusScorer` input list. The admin override path in `GeocodingService.set_official()` is unchanged.

**Single-result case:** If only one provider returns a match, its `confidence` is used directly. Consensus scoring with a single result does not penalize — `cluster_size=1`, `total_results=1`, `consensus_confidence = 1.0 * 1.0 = confidence`.

---

## Data Flow

### Full Cascade: Happy Path (typo in street name, exact providers find it after correction)

```
POST /geocode {"address": "489 Northministr Dr, Macon GA 31204"}
    |
    v
CascadeOrchestrator.resolve(freeform)
    |
    +-- [1] SpellCorrector.correct("489 Northministr Dr, Macon GA 31204")
    |         usaddress.tag() -> StreetName="Northministr"
    |         symspellpy -> "NORTHMINSTER"
    |         returns: "489 NORTHMINSTER DR MACON GA 31204"
    |
    +-- [2] canonical_key("489 NORTHMINSTER DR MACON GA 31204")
    |         -> normalized="489 NORTHMINSTER DR MACON GA 31204", hash=<sha256>
    |
    +-- [3] DB cache check by hash -> MISS
    |
    +-- [4] Exact provider dispatch
    |         OA -> GeocodingResult(lat=32.872, lng=-83.687, confidence=1.0)
    |         Tiger -> GeocodingResult(lat=32.872, lng=-83.687, confidence=0.95)
    |         Census -> GeocodingResult(lat=32.872, lng=-83.687, confidence=0.87)
    |         Any match? YES -> skip Stage 4 (fuzzy) and Stage 5 (LLM)
    |
    +-- [5] ConsensusScorer([oa_result, tiger_result, census_result])
    |         All three within 200m -> cluster_size=3
    |         Winner: oa_result (highest confidence=1.0)
    |         consensus_confidence = 1.0 * (3/3) = 1.0
    |
    +-- [6] Store remote results to DB (OA is local, not stored)
    |
    +-- [7] OfficialGeocoding -> ON CONFLICT DO UPDATE with census result
    |         (OA cannot be referenced by geocoding_result_id; it has no DB row)
    |         Use highest-confidence remote result as OfficialGeocoding target
    |
    v
return {official: census_result, local_results: [oa_result, tiger_result], cache_hit: false}
```

### Fuzzy Fallback Flow (degraded input, exact match fails)

```
POST /geocode {"address": "489 Northministr Dr, Macon"}   <- no zip, typo
    |
    +-- [1] SpellCorrector -> "489 NORTHMINSTER DR MACON"
    +-- [2] canonical_key -> normalized, hash
    +-- [3] cache miss
    +-- [4] All providers -> NO_MATCH (no zip; Tiger and Census fail; OA needs postcode)
    |
    +-- [Stage 4] FuzzyMatcher
    |         house_number="489", street_name="NORTHMINSTER DR", city="MACON"
    |         pg_trgm similarity query on openaddresses_points
    |         -> match: lat=32.872083, lng=-83.687444, similarity=0.92
    |         -> GeocodingResult(confidence=0.92*0.8=0.736, provider_name="fuzzy_oa")
    |
    +-- [5] ConsensusScorer([fuzzy_result]) -> winner=fuzzy_result (single result)
    +-- [6-7] Store + set OfficialGeocoding
    v
return {official: None (fuzzy has no DB row), local_results: [fuzzy_result]}
```

**Note on OfficialGeocoding and fuzzy results:** Fuzzy results are in-memory `GeocodingResult` dataclasses — they have no `geocoding_results` DB row and therefore no `id` to reference in `official_geocoding.geocoding_result_id`. For the v1.2 cascade, OfficialGeocoding can only be auto-set from results that exist in the DB (remote provider results). If the only successful result is fuzzy or LLM-corrected but resolved to a local provider, the response returns the result in `local_results` but leaves `official` as `None` (or retains any previously set official). This is an explicit design boundary.

### LLM Correction Flow (both exact and fuzzy fail)

```
POST /geocode {"address": "489 Northmisntr Dr, Macon GA 31204"}  <- severe typo
    |
    +-- [1-4] Exact providers -> NO_MATCH; FuzzyMatcher -> NO_MATCH
    |
    +-- [Stage 5] LLMAddressCorrector (CASCADE_LLM_ENABLED=true)
    |         POST /api/generate to Ollama
    |         response: {"corrected": "489 NORTHMINSTER DR MACON GA 31204", "changed": true}
    |
    +-- [Stage 5c] Re-enter cascade at Stage 1 with corrected string (attempt 2)
    |         SpellCorrector -> canonical_key -> exact providers
    |         Tiger -> GeocodingResult(confidence=0.95)
    |
    +-- [5] ConsensusScorer([tiger_result]) -> winner=tiger_result
    +-- [6-7] Store census result + set OfficialGeocoding
    v
return {official: tiger_result or census_result, cache_hit: false}
```

---

## Integration Points

### Where Each New Component Plugs In

| New Component | Plugs Into | Key Integration Detail |
|--------------|------------|------------------------|
| `SpellCorrector` | `CascadeOrchestrator`, Stage 1 | Called before `canonical_key()`. Input: raw freeform `str`. Output: corrected `str`. No changes to `normalization.py`. |
| `FuzzyMatcher` | `CascadeOrchestrator`, Stage 4 | Called after all providers return `confidence == 0.0`. Receives parsed address components. Queries `openaddresses_points` and `nad_points` directly via DB session. Returns `GeocodingResult` or `None`. |
| `LLMAddressCorrector` | `CascadeOrchestrator`, Stage 5 | Called after fuzzy fails AND `CASCADE_LLM_ENABLED=true`. Uses `app.state.http_client`. Returns corrected string or `None`. |
| `ConsensusScorer` | `CascadeOrchestrator`, Stage 6 | Receives `list[GeocodingResult]` (all providers combined). Returns `ConsensusResult` dataclass. No DB access. |
| `CascadeOrchestrator` | `GeocodingService.geocode()` | Gated by `CASCADE_ENABLED` env var (default `false`). When `false`, `GeocodingService` runs existing pipeline unchanged. |
| `_set_official_from_cascade()` | `GeocodingService` | New private method. Uses `ON CONFLICT DO UPDATE`. Called only from `CascadeOrchestrator`. Existing `_set_official()` with `DO NOTHING` is retained for non-cascade path. |

### What the Provider ABCs Do NOT Change

The `GeocodingProvider` and `ValidationProvider` ABCs (`providers/base.py`) require zero changes for v1.2. All five existing providers (Census, OA, Tiger, NAD, Macon-Bibb) are untouched. The cascade operates entirely on `GeocodingResult` schema objects already produced by existing provider calls.

### Docker Compose Changes for Ollama Sidecar

```yaml
# Additions to docker-compose.yml:

services:
  ollama:
    image: ollama/ollama:latest
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama
    environment:
      - OLLAMA_HOST=0.0.0.0
    # GPU support is opt-in. Omit deploy block for CPU-only dev environments.
    # deploy:
    #   resources:
    #     reservations:
    #       devices:
    #         - driver: nvidia
    #           count: all
    #           capabilities: [gpu]

  api:
    # existing config unchanged, add environment vars:
    environment:
      OLLAMA_BASE_URL: http://ollama:11434
      OLLAMA_MODEL: qwen2.5:1.5b
      CASCADE_ENABLED: "false"
      CASCADE_LLM_ENABLED: "false"
      CONSENSUS_DISTANCE_M: "200"
    depends_on:
      db:
        condition: service_healthy
      ollama:
        condition: service_started   # NOT service_healthy - Ollama has no health endpoint

volumes:
  postgres_data:   # existing
  ollama_data:     # NEW - persists downloaded models across container restarts
```

**Model pull:** Ollama does not auto-pull models on container start. Document the one-time manual step: `docker exec <container> ollama pull qwen2.5:1.5b`. Do not automate model pull in the API startup lifespan — it adds a 1-2 GB download to every fresh container start and can fail mid-pull silently.

**Feature flag default `false`:** With both `CASCADE_ENABLED=false` and `CASCADE_LLM_ENABLED=false`, the Ollama container starts but receives zero requests. Developers can enable the cascade locally without modifying the compose file by setting env vars. The existing pipeline is the default for all environments.

---

## New Components: Detailed Specifications

### SpellCorrector (`correction/spell.py`)

**Library:** `symspellpy` v6.9.0. Add to `pyproject.toml` dependencies.

**Initialization:** Loaded once at module import time (or lazily on first call). The dictionary file from the symspellpy package is loaded with `max_dictionary_edit_distance=2` and `prefix_length=7` — the SymSpell defaults, which provide a good balance of correction coverage and speed.

**Correction scope:** Parse input with `usaddress.tag()`. Correct only tokens with label `StreetName`. Do not correct: `AddressNumber`, `StreetNamePreDirectional`, `StreetNamePostDirectional`, `StreetNamePostType`, `PlaceName`, `StateName`, `ZipCode`.

**Fallback:** If `usaddress.tag()` fails with `RepeatedLabelError`, return the original input string unchanged.

### FuzzyMatcher (`correction/fuzzy.py`)

**Database extensions required (add to new Alembic migration):**
- `CREATE EXTENSION IF NOT EXISTS pg_trgm;` — not currently enabled
- `fuzzystrmatch` — already enabled as Tiger prerequisite, no action needed

**GIN indexes required (same Alembic migration):**
```sql
CREATE INDEX IF NOT EXISTS idx_oa_street_trgm
    ON openaddresses_points USING gin(street gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_nad_street_trgm
    ON nad_points USING gin(street_name gin_trgm_ops);
```

**pg_trgm threshold:** 0.6 (similarity > 0.6). Do not lower below 0.5 — false positives increase rapidly and degrade confidence scores. Note: `word_similarity()` is preferred over `similarity()` for street name matching because it handles the case where the query token is a substring of the stored value (e.g., `NORTHMINSTER` matching `NORTHMINSTER DR` in the stored field).

**Query tables:** `openaddresses_points` first, then `nad_points`. Do not query Tiger via fuzzy — the Tiger geocoder has its own internal fuzzy tolerance.

**Confidence cap:** max 0.8 regardless of similarity score. Fuzzy results are inherently less certain than exact matches.

### LLMAddressCorrector (`correction/llm.py`)

**HTTP call:**
```python
response = await http_client.post(
    f"{ollama_base_url}/api/generate",
    json={
        "model": model_name,
        "prompt": prompt,
        "stream": False,
        "format": "json",
    },
    timeout=10.0,
)
data = response.json()
result = json.loads(data["response"])  # Ollama wraps structured output in "response" key
```

**JSON parse failure:** If the response cannot be parsed as JSON or the `corrected` key is missing, return `None` — treat as no correction available.

### ConsensusScorer (`correction/consensus.py`)

**Output dataclass:**
```python
@dataclass
class ConsensusResult:
    winner: GeocodingResult       # Best result from largest cluster
    cluster_size: int             # How many providers agreed
    total_results: int            # Total providers with confidence > 0.0
    outliers: list[GeocodingResult]  # Results outside the cluster
    consensus_confidence: float   # winner.confidence * (cluster_size / total_results)
```

**Edge cases:**
- Empty input (all results `confidence == 0.0`): return `None`.
- Single result: `cluster_size=1`, `total_results=1`, `consensus_confidence = winner.confidence`.
- All results agree (within threshold): `cluster_size == total_results`, no outliers.
- All results disagree: pick the cluster with the highest average confidence.

---

## Suggested Build Order

This order respects component dependencies and keeps each phase independently testable.

| Step | Component | Rationale |
|------|-----------|-----------|
| 1 | `SpellCorrector` + unit tests | Pure Python, no DB, no Docker changes. Testable in isolation. Establish the `str -> str` contract. |
| 2 | New Alembic migration: pg_trgm extension + GIN indexes | Schema change independent of any application code. Can be applied immediately to dev DB. |
| 3 | `FuzzyMatcher` + integration tests against dev DB | Depends only on the migration from step 2 and the existing staging tables. No service layer changes. |
| 4 | `ConsensusScorer` + unit tests | Pure Python, no DB, no Docker. Input is `list[GeocodingResult]` fixtures. |
| 5 | `CascadeOrchestrator` (Stages 1-4, 6-7, no LLM yet) | Wire SpellCorrector + existing providers + FuzzyMatcher + ConsensusScorer. Full cascade flow without Ollama. Gate with `CASCADE_ENABLED=false` default. |
| 6 | Modify `GeocodingService` to delegate to `CascadeOrchestrator` | Minimal change: check `CASCADE_ENABLED` env var, delegate when true. Existing code path untouched when disabled. |
| 7 | Update OfficialGeocoding auto-set (`_set_official_from_cascade()`) | New method using `ON CONFLICT DO UPDATE`. Existing `DO NOTHING` path preserved for non-cascade. |
| 8 | Docker Compose `ollama` service + `LLMAddressCorrector` | Last because it requires infrastructure change and has the most risk. Gate behind `CASCADE_LLM_ENABLED=false` default. |
| 9 | Automated end-to-end tests (Playwright/Chrome DevTools MCP) | Test all stages using the degraded-input test cases from the E2E test report (4 addresses with known provider defects). |

---

## Anti-Patterns

### Anti-Pattern 1: FuzzyMatcher Implemented as a GeocodingProvider

**What people do:** Implement fuzzy matching as another `GeocodingProvider` subclass registered in `app.state.providers`, called alongside exact providers on every request.

**Why it's wrong:** Fuzzy matching against the same staging tables that OA and NAD query re-queries those tables on every request, not just as a fallback. The provider ABC implies an independent data source — fuzzy is a query strategy on existing data. This also breaks the cascade ordering (fuzzy must only run when exact fails).

**Do this instead:** `FuzzyMatcher` in `correction/fuzzy.py`, called explicitly by `CascadeOrchestrator` only after all providers return `confidence == 0.0`.

### Anti-Pattern 2: Spell Correction After scourgify

**What people do:** Run spell correction on the scourgify-normalized output or on the canonical hash form.

**Why it's wrong:** scourgify parses using USPS abbreviation tables. A misspelled street name causes scourgify to either fail entirely (uppercase fallback) or produce a garbled normalization. The SHA-256 hash is then wrong and will never match any cache or staging table record. Correcting after the fact is too late.

**Do this instead:** `SpellCorrector` runs on raw freeform input. Its corrected output is passed to `canonical_key()`. The corrected string gets a different hash than the original misspelling — this is the correct behavior.

### Anti-Pattern 3: Keeping ON CONFLICT DO NOTHING for the Cascade Path

**What people do:** Retain the existing `ON CONFLICT DO NOTHING` in OfficialGeocoding upserts within the cascade, assuming first-write is still correct.

**Why it's wrong:** The cascade collects results from multiple stages (exact, fuzzy, LLM-corrected) and scores them. If Census is called first and returns a low-confidence result, `DO NOTHING` locks in that result and silently discards the higher-confidence Tiger or OA result found later. The consensus scoring is then pointless.

**Do this instead:** Use `ON CONFLICT DO UPDATE` in the cascade path via `_set_official_from_cascade()`. The `CascadeOrchestrator` determines the winner before writing to OfficialGeocoding. The non-cascade path (`GeocodingService.geocode()` called directly without cascade enabled) retains `DO NOTHING`.

### Anti-Pattern 4: Requiring Ollama Healthy Before API Startup

**What people do:** Set `condition: service_healthy` for the Ollama dependency in `depends_on`.

**Why it's wrong:** Ollama has no official health check endpoint. CPU model inference for the first request after cold start takes 10-60 seconds (model load time). Blocking API startup on Ollama readiness makes every `docker compose up` take over a minute and makes the API fragile in environments without Ollama.

**Do this instead:** Use `condition: service_started`. `LLMAddressCorrector` handles `ConnectError` gracefully. The default `CASCADE_LLM_ENABLED=false` means the API works identically whether or not Ollama is running.

### Anti-Pattern 5: Applying Consensus Scoring to Admin Overrides

**What people do:** Include `provider_name == "admin_override"` results in the `ConsensusScorer` input list, letting them be voted down by provider consensus.

**Why it's wrong:** Admin overrides represent explicit human authority. If an admin has set the official coordinates for an address, consensus among automated providers should never change it. The existing `set_official()` method already prevents this — the anti-pattern is forgetting to filter overrides before calling `ConsensusScorer`.

**Do this instead:** `CascadeOrchestrator` checks for an existing admin override before running the cascade. If one exists, return it directly without running any cascade stages.

---

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| Current (Macon-Bibb county, internal API) | Monolith is fine. Cascade adds 50-200ms latency per non-cached request on CPU (spell correction + fuzzy SQL query). LLM stage adds 1-5s when enabled. |
| Multi-county / multi-state | FuzzyMatcher queries must add a `state` and/or `postcode` filter to avoid full-table scans across 80M NAD rows. GIN indexes alone are insufficient for a full NAD scan without a state filter. |
| High-concurrency batch requests | LLM sidecar is the cascade bottleneck (serial inference). Add `asyncio.Semaphore(2)` in `LLMAddressCorrector` to cap concurrent Ollama requests. The rest of the cascade is IO-bound and handles concurrency natively via asyncpg connection pooling. |

---

## Sources

- Codebase inspection: `src/civpulse_geo/services/geocoding.py` — existing pipeline stages, `ON CONFLICT DO NOTHING`, first-writer-wins logic, `_get_official()` (HIGH confidence)
- Codebase inspection: `src/civpulse_geo/providers/base.py` — `GeocodingProvider` / `ValidationProvider` ABCs, `is_local` property (HIGH confidence)
- Codebase inspection: `src/civpulse_geo/normalization.py` — scourgify integration point, `canonical_key()` input/output (HIGH confidence)
- Codebase inspection: `src/civpulse_geo/main.py` — conditional provider registration, `app.state.http_client`, lifespan pattern (HIGH confidence)
- Codebase inspection: `docker-compose.yml` — existing two-service topology (HIGH confidence)
- [PostgreSQL 17 fuzzystrmatch docs](https://www.postgresql.org/docs/17/fuzzystrmatch.html) — Soundex, Metaphone, Double Metaphone function signatures; already enabled for Tiger (HIGH confidence)
- [PostgreSQL 17 pg_trgm docs](https://www.postgresql.org/docs/17/pgtrgm.html) — `similarity()`, `word_similarity()`, GIN index pattern, threshold defaults (HIGH confidence)
- [symspellpy GitHub](https://github.com/mammothb/symspellpy) — v6.9.0 current release (March 2025), SymSpell algorithm Python port (MEDIUM confidence — API details confirmed via readthedocs)
- [Ollama Docker docs](https://docs.ollama.com/docker) — service configuration, volume persistence, GPU opt-in `deploy` block (MEDIUM confidence)
- [EarthDaily geocoding consensus algorithm](https://earthdaily.com/blog/geocoding-consensus-algorithm-a-foundation-for-accurate-risk-address-risk-assessment) — multi-provider consensus scoring patterns (MEDIUM confidence)

---

## v1.1 Architecture (Reference — No Changes in v1.2)

The section below is preserved from the v1.1 research (2026-03-20). The v1.2 cascade builds on top of this architecture without modifying any of the components described here.

---

### System Overview (v1.1)

```
┌──────────────────────────────────────────────────────────────────┐
│                         Router Layer                              │
│   POST /geocode   POST /validate   POST /geocode/batch  ...      │
└───────────────────────────┬──────────────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────────────┐
│                        Service Layer                              │
│                                                                   │
│  GeocodingService.geocode()         ValidationService.validate() │
│  ┌─────────────────────────────┐   ┌──────────────────────────┐  │
│  │  provider.is_local?         │   │  provider.is_local?      │  │
│  │  YES -> call + return direct│   │  YES -> call + return    │  │
│  │  NO  -> cache-first pipeline│   │  NO  -> cache-first      │  │
│  └─────────────────────────────┘   └──────────────────────────┘  │
└──────────────┬────────────────────────────┬──────────────────────┘
               │                            │
 ┌─────────────▼──────────────┐   ┌─────────▼────────────────────┐
 │   Remote Providers          │   │  Local Providers              │
 │  (HTTP + DB cache)          │   │  (no DB writes)               │
 │  CensusGeocodingProvider    │   │  OAGeocodingProvider          │
 │  ScourgifyValidationProv.   │   │  NADGeocodingProvider         │
 └────────────────────────────┘   │  TigerGeocodingProvider       │
                                   │  MaconBibbGeocodingProvider   │
                                   └──────────────────────────────┘
               │                            │
 ┌─────────────▼──────────────────────────────────────────────────┐
 │                        Data Layer                               │
 │  addresses, geocoding_results, official_geocoding               │
 │  validation_results, admin_overrides                            │
 │  openaddresses_points, nad_points, macon_bibb_points            │
 │  tiger.* (built-in PostGIS schema)                              │
 └─────────────────────────────────────────────────────────────────┘
```

For full v1.1 component details, provider implementation patterns, CLI bulk load patterns, and staging table schemas, see the build records in `.planning/phases/` and `.planning/milestones/`.

---

*Architecture research for: CivPulse Geo API v1.2 Cascading Address Resolution*
*Researched: 2026-03-29*

---

---

# v1.3 Architecture: Production Deployment, Observability, and CI/CD

**Domain:** CivPulse Geo API — v1.3 Production Readiness & Deployment
**Researched:** 2026-03-29
**Confidence:** HIGH for integration patterns (codebase inspection + official docs); MEDIUM for specific package versions (verified via PyPI/official docs)

---

## System Overview: v1.3 Deployment Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  CI/CD Pipeline (GitHub Actions)                                             │
│  push to main -> build multi-stage image -> push ghcr.io -> ArgoCD sync    │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │ image tag update (kustomize / values.yaml)
┌────────────────────────────────▼────────────────────────────────────────────┐
│  K8s Cluster (k3s, civpulse-dev / civpulse-prod namespace)                  │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  Pod: geo-api                                                         │   │
│  │  ┌─────────────────────┐  ┌──────────────────────────────────────┐   │   │
│  │  │  init: wait-for-db  │  │  init: alembic-migrate               │   │   │
│  │  │  (busybox pg_isready)│  │  (same image, `alembic upgrade head`)│   │   │
│  │  └─────────────────────┘  └──────────────────────────────────────┘   │   │
│  │  ┌─────────────────────────────────────────────────────────────────┐ │   │
│  │  │  container: geo-api                                              │ │   │
│  │  │  uvicorn civpulse_geo.main:app --host 0.0.0.0 --port 8000       │ │   │
│  │  │  OTel SDK initialized at startup (traces -> OTLP -> Tempo)      │ │   │
│  │  │  Loguru JSON sink -> stdout -> Alloy -> Loki                    │ │   │
│  │  │  Prometheus /metrics endpoint -> VictoriaMetrics                 │ │   │
│  │  └─────────────────────────────────────────────────────────────────┘ │   │
│  │  ┌─────────────────────────────────────────────────────────────────┐ │   │
│  │  │  sidecar: ollama                                                  │ │   │
│  │  │  image: ollama/ollama:latest                                     │ │   │
│  │  │  port: 11434 (localhost only - same pod network)                 │ │   │
│  │  │  volume: ollama-pvc -> /root/.ollama                             │ │   │
│  │  └─────────────────────────────────────────────────────────────────┘ │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  Service: geo-api (ClusterIP :8000) — internal only, no Ingress             │
│                                                                              │
│  External: postgresql.civpulse-infra.svc.cluster.local:5432                │
└─────────────────────────────────────────────────────────────────────────────┘
                                 │
┌────────────────────────────────▼────────────────────────────────────────────┐
│  Observability Stack (pre-existing cluster infrastructure)                   │
│  Grafana Alloy (DaemonSet) -> collects stdout/stderr from all pods          │
│  Alloy -> Loki (logs)                                                        │
│  API OTLP exporter -> Tempo (traces, gRPC :4317)                            │
│  Alloy prometheus.scrape -> VictoriaMetrics (metrics, /metrics :8000)      │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Component Map: New vs Modified vs Unchanged

| Component | Status | What Changes |
|-----------|--------|--------------|
| `Dockerfile` | MODIFIED | Multi-stage builder/runtime split; non-root user; read-only FS support |
| `src/civpulse_geo/main.py` | MODIFIED | OTel SDK initialization in lifespan before providers load; Loguru JSON sink setup |
| `src/civpulse_geo/config.py` | MODIFIED | New OTel/observability settings: `OTEL_ENDPOINT`, `OTEL_SERVICE_NAME`, `LOG_FORMAT` |
| `src/civpulse_geo/api/health.py` | MODIFIED | Add `/health/live` (liveness) and `/health/ready` (readiness) endpoints |
| `k8s/geo-api-deployment.yaml` | NEW | Deployment with init containers, security context, resource limits |
| `k8s/geo-api-service.yaml` | NEW | ClusterIP Service on port 8000 |
| `k8s/geo-api-configmap.yaml` | NEW | Non-secret env vars (LOG_FORMAT, OTEL_ENDPOINT, etc.) |
| `k8s/geo-api-secret.yaml` | NEW | DATABASE_URL, DATABASE_URL_SYNC (managed via ArgoCD / sealed secrets) |
| `k8s/argocd-app-dev.yaml` | NEW | ArgoCD Application for civpulse-dev namespace |
| `k8s/argocd-app-prod.yaml` | NEW | ArgoCD Application for civpulse-prod namespace |
| `k8s/ollama-deployment.yaml` | EXISTING | Already created; needs security context + resource limits review |
| `.github/workflows/ci.yml` | NEW | Test, lint, build, push to GHCR, update image tag |
| All providers, services, models | UNCHANGED | Zero changes to business logic |
| `docker-compose.yml` | UNCHANGED | Dev environment remains as-is |

---

## Architectural Patterns

### Pattern 1: Multi-Stage Dockerfile with uv (Builder/Runtime Split)

**What:** Two-stage build separating dependency installation (builder) from the minimal runtime image. The builder compiles bytecode and installs all dependencies. The runtime stage receives only the `.venv` and application source — no build tools, no uv binary, no cache.

**Why this structure:** The existing single-stage Dockerfile runs as root, installs build tools into the runtime image, and does not support a read-only filesystem. The K8s security context requires non-root UID and a read-only root filesystem. Multi-stage reduces the attack surface and image size.

**Key ENV vars for the runtime stage:**
```dockerfile
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PATH="/app/.venv/bin:$PATH"
ENV UV_NO_SYNC=1
```

`PYTHONDONTWRITEBYTECODE=1` prevents `.pyc` writes at runtime (required for read-only FS). `UV_NO_SYNC=1` prevents uv from attempting re-installation at runtime. Bytecode must be pre-compiled during build with `uv sync --compile-bytecode`.

**Non-root user pattern:**
```dockerfile
# In builder stage:
RUN uv sync --locked --no-editable --compile-bytecode

# In runtime stage:
RUN groupadd --gid 1001 appgroup && \
    useradd --uid 1001 --gid appgroup --no-create-home appuser
COPY --from=builder --chown=appuser:appgroup /app /app
USER appuser
```

**Read-only filesystem:** The only writable path needed at runtime is for Python's `tempfile` (used by some libraries). Mount `/tmp` as `emptyDir` in K8s. No uv cache directory is needed at runtime.

**System library concern:** The existing Dockerfile installs `libgdal-dev`, `postgis`, `postgresql-client`, `fiona` native libs. These must remain in the runtime stage (they are runtime dependencies of fiona/GDAL, not build tools). The builder stage handles the Python build; the runtime stage must include the same `apt-get install` block.

**Trade-offs:** Image size reduction is limited by fiona/GDAL native libs (unavoidable ~200MB). The main benefit is non-root execution and cleaner layer separation.

### Pattern 2: OpenTelemetry SDK Initialization in lifespan

**What:** The OTel TracerProvider, OTLP exporter, and BatchSpanProcessor are configured once at application startup inside the `lifespan` context manager, before any provider registration. The SDK is initialized globally via `trace.set_tracer_provider()`. Library instrumentation (`FastAPIInstrumentor`, `SQLAlchemyInstrumentor`) is called once after the TracerProvider is set.

**Critical ordering — must execute before `FastAPI()` is instantiated:**
```python
# telemetry.py (new module)
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

def setup_telemetry(app, engine, settings):
    exporter = OTLPSpanExporter(endpoint=settings.otel_endpoint)
    provider = TracerProvider(
        resource=Resource.create({"service.name": settings.otel_service_name})
    )
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    # Instrument after provider is set
    FastAPIInstrumentor.instrument_app(app)
    # Pass sync_engine for SQLAlchemy async engine instrumentation
    SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)
```

`FastAPIInstrumentor.instrument_app(app)` must be called after `app = FastAPI(...)` but before the app starts serving requests. In the lifespan pattern, this is called at the start of the `lifespan` async context manager.

**OTLP endpoint:** `OTEL_ENDPOINT=http://tempo.civpulse-infra.svc.cluster.local:4317` (gRPC). This is the Grafana Tempo OTLP ingestion endpoint already running in the cluster. Use gRPC (port 4317) not HTTP (port 4318) — gRPC is lower overhead for high-throughput span export.

**When OTel is disabled (dev mode):** If `OTEL_ENDPOINT` is empty or `OTEL_ENABLED=false`, use a `NoOpTracerProvider` — do not attempt connection. This keeps local Docker Compose development working without a Tempo instance.

**SQLAlchemy async engine note:** `SQLAlchemyInstrumentor` requires the synchronous engine handle: `engine.sync_engine`. This is available on any `AsyncEngine` instance from SQLAlchemy 2.0. The existing `database.py` creates an `AsyncEngine` — pass it to `setup_telemetry()` at startup.

**Packages required (add to pyproject.toml):**
```
opentelemetry-api
opentelemetry-sdk
opentelemetry-exporter-otlp-proto-grpc
opentelemetry-instrumentation-fastapi
opentelemetry-instrumentation-sqlalchemy
opentelemetry-instrumentation-httpx
```

`opentelemetry-instrumentation-httpx` instruments the existing `app.state.http_client` (Census Geocoder calls + Ollama calls) automatically — add it to get trace context propagation to external HTTP calls.

### Pattern 3: Loguru JSON Sink for Kubernetes Log Collection

**What:** Loguru is reconfigured at startup to output structured JSON to `stdout` (not `stderr`) when running in a container environment. Grafana Alloy collects pod `stdout` and ships to Loki. JSON format enables Loki's structured log parsing and label extraction.

**Loguru JSON sink setup:**
```python
import sys
from loguru import logger

def configure_logging(settings):
    logger.remove()  # Remove the default stderr sink
    if settings.log_format == "json":
        logger.add(
            sys.stdout,
            format="{message}",   # serialize=True handles the format
            serialize=True,       # Outputs JSON with all fields
            level=settings.log_level,
            enqueue=True,         # Async-safe — required for FastAPI async context
        )
    else:
        # Human-readable for local dev
        logger.add(sys.stderr, level=settings.log_level, colorize=True)
```

`serialize=True` produces JSON with keys: `text` (message), `record` (level, time, name, function, line, extra). Alloy parses this using `loki.source.kubernetes_logs` + `loki.process` with a JSON stage.

**Trace context injection:** Loguru does not natively propagate OTel trace context into log records. The bridge is a `patcher` function that reads the current span from the OTel context and injects `trace_id` and `span_id` into Loguru's `extra` dict:
```python
from opentelemetry import trace as otel_trace

def inject_trace_context(record):
    span = otel_trace.get_current_span()
    ctx = span.get_span_context()
    if ctx and ctx.is_valid:
        record["extra"]["trace_id"] = format(ctx.trace_id, "032x")
        record["extra"]["span_id"] = format(ctx.span_id, "016x")

logger.configure(patcher=inject_trace_context)
```

This is called once at startup after `setup_telemetry()` so the OTel provider is already set. The `trace_id` field in every log record enables Grafana's Loki-to-Tempo trace correlation: clicking a trace ID in Loki jumps directly to the Tempo trace.

**Log level config:** `LOG_LEVEL=INFO` in production, `LOG_LEVEL=DEBUG` in dev. Loguru's `LOG_LEVEL` maps directly to the existing `settings.log_level` field — no new settings key needed. Add `LOG_FORMAT=json` as a new setting (default `"text"` for local dev).

**Alloy collection:** Alloy's DaemonSet scrapes pod stdout using `loki.source.kubernetes_logs`. No changes needed to Alloy config — it already collects all pod stdout. The JSON format makes log parsing more reliable. Alloy adds K8s metadata labels (`namespace`, `pod`, `container`) automatically.

### Pattern 4: Health Endpoints for K8s Probes

**What:** The existing `/health` endpoint combines liveness and readiness in one call. K8s requires separate liveness and readiness probes for correct behavior. A liveness probe that depends on a DB connection will restart healthy pods when the DB is temporarily unavailable — this is wrong. Liveness should test only that the process is alive.

**Correct probe split:**

```python
@router.get("/health/live")
async def liveness():
    """K8s liveness probe — process is alive, no DB dependency."""
    return {"status": "alive"}

@router.get("/health/ready")
async def readiness(db: AsyncSession = Depends(get_db)):
    """K8s readiness probe — DB connected, providers loaded."""
    try:
        await db.execute(text("SELECT 1"))
        return {"status": "ready"}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"not ready: {exc}")
```

The existing `/health` endpoint is retained for backward compatibility (other CivPulse services may call it). The new `/health/live` and `/health/ready` are added alongside.

**K8s probe config:**
```yaml
livenessProbe:
  httpGet:
    path: /health/live
    port: 8000
  initialDelaySeconds: 10
  periodSeconds: 30
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /health/ready
    port: 8000
  initialDelaySeconds: 15
  periodSeconds: 10
  failureThreshold: 6
```

Readiness `initialDelaySeconds: 15` accounts for lifespan startup time (spell corrector dictionary load + provider availability checks against DB).

### Pattern 5: Init Containers for Migration Sequencing

**What:** Two init containers run sequentially before the main geo-api container starts. First: wait for PostgreSQL to be reachable. Second: run `alembic upgrade head`. This replaces the inline wait-and-migrate logic in `scripts/docker-entrypoint.sh`.

**Why init containers instead of entrypoint script:** In K8s, if the entrypoint script blocks waiting for DB, the pod is stuck in `Running` state but not ready. Init containers provide proper pod lifecycle signaling — the pod stays in `Init` state until init containers complete, then transitions to `Running`. This prevents the service from receiving traffic before migrations are complete.

**Init container 1 — wait for DB:**
```yaml
initContainers:
  - name: wait-for-db
    image: busybox:latest
    command: ["sh", "-c"]
    args:
      - |
        until nc -z postgresql.civpulse-infra.svc.cluster.local 5432; do
          echo "waiting for database..."; sleep 2
        done
        echo "database is ready"
```

**Init container 2 — run migrations:**
```yaml
  - name: alembic-migrate
    image: ghcr.io/civpulse/geo-api:${IMAGE_TAG}
    command: ["alembic", "upgrade", "head"]
    env:
      - name: DATABASE_URL_SYNC
        valueFrom:
          secretKeyRef:
            name: geo-api-secret
            key: DATABASE_URL_SYNC
```

The migration init container uses the same application image (no separate migration image needed). It runs `alembic upgrade head` directly — the `alembic` CLI is in the `.venv/bin` path. The `DATABASE_URL_SYNC` secret provides the psycopg2 URL for Alembic.

**Concurrency concern:** With multiple pod replicas, multiple init containers may attempt `alembic upgrade head` simultaneously. Alembic 1.x uses an advisory lock on the `alembic_version` table during migration — concurrent runs are safe. Only one will apply the migration; others will see it already applied and exit 0.

### Pattern 6: Graceful Shutdown with preStop Hook

**What:** Kubernetes sends SIGTERM to PID 1 in the container when a pod is terminating. Uvicorn responds to SIGTERM by stopping acceptance of new connections and draining in-flight requests. However, K8s endpoints are not immediately updated — new requests can still be routed to the terminating pod for several seconds after SIGTERM.

**The problem:** If Uvicorn starts refusing connections immediately on SIGTERM but K8s still routes traffic to the pod for 5-15 seconds, clients see connection refused errors. This causes failed requests during rolling deployments.

**Solution — preStop sleep:**
```yaml
lifecycle:
  preStop:
    exec:
      command: ["sh", "-c", "sleep 5"]
```

The preStop hook runs before SIGTERM is sent. A 5-second sleep gives the K8s control plane time to remove the pod from service endpoints before Uvicorn starts its shutdown. Combined with Uvicorn's `--timeout-graceful-shutdown 30` flag, in-flight requests complete before the process exits.

**Uvicorn invocation in K8s (exec form, not shell form):**
```yaml
command: ["uvicorn", "civpulse_geo.main:app", "--host", "0.0.0.0", "--port", "8000",
          "--workers", "1", "--timeout-graceful-shutdown", "30"]
```

Use exec form (JSON array) not shell form (string) so uvicorn is PID 1 and receives SIGTERM directly. The existing `docker-entrypoint.sh` uses `exec uvicorn ...` which correctly passes PID 1 to uvicorn — the K8s Deployment should replicate this by using exec form CMD.

### Pattern 7: ArgoCD GitOps — Image Tag Update Strategy

**What:** The CI/CD pipeline builds and pushes a new image to GHCR, then updates the image tag in the K8s manifests repo (or a `kustomization.yaml` overlay). ArgoCD detects the change and syncs the Deployment.

**Image tag strategy:** Use the git commit SHA (short) as the image tag, not `latest`. This provides deterministic rollback and prevents ArgoCD from reconciling to an indeterminate state.

```yaml
# In CI workflow:
IMAGE_TAG=$(git rev-parse --short HEAD)
docker build -t ghcr.io/civpulse/geo-api:${IMAGE_TAG} .
docker push ghcr.io/civpulse/geo-api:${IMAGE_TAG}
# Then update k8s/kustomization.yaml or values.yaml with new tag
```

**ArgoCD Application structure:**
```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: geo-api-dev
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/civpulse/geo-api
    targetRevision: HEAD
    path: k8s/overlays/dev
  destination:
    server: https://kubernetes.default.svc
    namespace: civpulse-dev
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
```

**Dev vs Prod overlay:** Use Kustomize overlays (`k8s/base/` + `k8s/overlays/dev/` + `k8s/overlays/prod/`). The base defines the Deployment, Service, ConfigMap. Overlays patch the image tag, replica count, and namespace. This prevents prod from auto-syncing on dev image pushes.

### Pattern 8: Ollama as Sidecar Container (Not Separate Deployment)

**What:** In K8s, Ollama runs as a sidecar container within the same pod as geo-api, not as a separate Deployment+Service. The existing `k8s/ollama-deployment.yaml` deploys Ollama as a standalone Deployment — this is appropriate for a shared Ollama instance, but for geo-api's use case (single consumer, tight coupling, localhost-only communication), a sidecar is preferable.

**Why sidecar over separate Deployment:**
- geo-api calls Ollama at `http://localhost:11434` (same pod network namespace) — no Service DNS needed
- Pod lifecycle coupling is correct — Ollama should start/stop with geo-api
- PVC (ollama-pvc) persists the model across pod restarts regardless of sidecar vs standalone

**Sidecar container spec within geo-api Deployment:**
```yaml
- name: ollama
  image: ollama/ollama:latest
  ports:
    - containerPort: 11434
  resources:
    requests:
      memory: "2Gi"
      cpu: "500m"
    limits:
      memory: "4Gi"
  volumeMounts:
    - name: ollama-data
      mountPath: /root/.ollama
  readinessProbe:
    httpGet:
      path: /api/tags
      port: 11434
    initialDelaySeconds: 30
    periodSeconds: 15
    failureThreshold: 6
```

**Model pre-pull init container:** The existing `k8s/ollama-deployment.yaml` already has a `model-pull` init container that pulls `qwen2.5:3b` before Ollama starts. This pattern is correct and should be preserved. The PVC ensures the model is only downloaded once across restarts.

**OLLAMA_URL in geo-api:** Set `OLLAMA_URL=http://localhost:11434` in the K8s ConfigMap (vs `http://ollama:11434` used when Ollama is a separate Service). The existing `settings.ollama_url` in `config.py` reads from this env var — no code change needed.

---

## Data Flow

### Request Trace Flow (happy path with OTel instrumentation)

```
HTTP client (run-api / vote-api)
    |
    | HTTP POST /geocode (trace context propagated via W3C traceparent header)
    v
FastAPI ASGI middleware (FastAPIInstrumentor)
    | -> creates root span: "POST /geocode"
    | -> trace_id injected into Loguru extra via patcher
    |
    v
GeocodingService.geocode()  [manual span: "geocoding.geocode"]
    |
    +-- asyncpg query (SQLAlchemyInstrumentor)
    |       -> child span: "SELECT addresses" (DB call)
    |
    +-- CascadeOrchestrator.resolve()  [manual span: "cascade.resolve"]
    |   |
    |   +-- SpellCorrector.correct()  [no span - sub-ms, not worth the overhead]
    |   |
    |   +-- provider dispatch  [manual span per provider: "provider.openaddresses"]
    |   |       -> asyncpg queries -> child DB spans
    |   |
    |   +-- ConsensusScorer  [no span - pure computation]
    |
    v
JSON response
    |
FastAPIInstrumentor closes root span
    |
BatchSpanProcessor buffers span
    |
OTLPSpanExporter -> gRPC -> Tempo (civpulse-infra)
```

**Log correlation:** Every log emitted during a request carries `trace_id` in the JSON `extra` field (injected by the Loguru patcher). Alloy ships log JSON to Loki. In Grafana, selecting a trace in Tempo shows the correlated logs in Loki via the `trace_id` label.

### CI/CD Deployment Flow

```
git push origin main
    |
    v
GitHub Actions: ci.yml
    |
    +-- [job: test]  uv run pytest tests/ (all 504 tests)
    +-- [job: lint]  uv run ruff check src/
    |
    v (on test pass)
    +-- [job: build-push]
    |       docker/setup-buildx-action
    |       docker/login-action (GITHUB_TOKEN -> ghcr.io)
    |       docker/build-push-action
    |           --build-arg GIT_COMMIT=$(git rev-parse --short HEAD)
    |           --tag ghcr.io/civpulse/geo-api:${SHORT_SHA}
    |           --tag ghcr.io/civpulse/geo-api:latest
    |
    v (on push success)
    +-- [job: update-manifests]
    |       kustomize edit set image geo-api=ghcr.io/civpulse/geo-api:${SHORT_SHA}
    |       git commit + push k8s/overlays/dev/kustomization.yaml
    |
    v
ArgoCD detects manifest change -> syncs civpulse-dev Deployment
    |
    v
K8s rolling update:
    new pod starts -> init containers run -> migrations applied -> geo-api starts
    readiness probe passes -> new pod added to Service endpoints
    old pod receives SIGTERM -> preStop sleep -> graceful drain -> terminated
```

### Log Pipeline Flow

```
geo-api container (uvicorn)
    | Loguru serialize=True -> JSON to stdout
    v
K8s container runtime captures stdout
    |
Grafana Alloy DaemonSet (loki.source.kubernetes_logs)
    | adds labels: namespace, pod, container, node
    | loki.process: parse JSON body, extract level/trace_id as labels
    v
Loki
    |
Grafana dashboard: query by namespace=civpulse-dev, trace_id=<id>
```

---

## New Files Required

### `k8s/` manifest structure

```
k8s/
├── base/
│   ├── deployment.yaml          # geo-api Deployment (Ollama sidecar, init containers)
│   ├── service.yaml             # ClusterIP Service :8000
│   ├── configmap.yaml           # Non-secret env vars
│   └── kustomization.yaml       # Base kustomization
├── overlays/
│   ├── dev/
│   │   ├── kustomization.yaml   # Image tag, namespace patch (civpulse-dev)
│   │   └── patch-replicas.yaml  # replicas: 1 for dev
│   └── prod/
│       ├── kustomization.yaml   # Image tag, namespace patch (civpulse-prod)
│       └── patch-replicas.yaml  # replicas: 2 for prod
├── argocd-app-dev.yaml          # ArgoCD Application CR (civpulse-dev)
├── argocd-app-prod.yaml         # ArgoCD Application CR (civpulse-prod)
├── ollama-deployment.yaml       # EXISTING (standalone, shared instance)
├── ollama-service.yaml          # EXISTING
└── ollama-pvc.yaml              # EXISTING
```

**Note on standalone vs sidecar Ollama:** The existing `k8s/ollama-*.yaml` files deploy Ollama as a standalone Deployment for shared cluster use. The geo-api Deployment references Ollama via `OLLAMA_URL=http://ollama.civpulse-dev.svc.cluster.local:11434` when using the standalone pattern. Either pattern works — the `OLLAMA_URL` env var is the only coupling point.

### `.github/workflows/ci.yml` structure

```yaml
name: CI
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgis/postgis:17-3.5
        env: {POSTGRES_DB: test_geo, POSTGRES_USER: civpulse, POSTGRES_PASSWORD: civpulse}
        options: --health-cmd "pg_isready" --health-interval 5s --health-retries 10
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv sync --locked
      - run: uv run ruff check src/
      - run: uv run pytest tests/ -x --ignore=tests/cli

  build-push:
    needs: test
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    permissions:
      contents: write
      packages: write
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - uses: docker/build-push-action@v6
        with:
          push: true
          build-args: GIT_COMMIT=${{ github.sha }}
          tags: |
            ghcr.io/${{ github.repository_owner }}/geo-api:${{ github.sha }}
            ghcr.io/${{ github.repository_owner }}/geo-api:latest
```

---

## Integration Points: Existing Code Changes

### `main.py` Modifications

The lifespan function requires two additions at the very start (before provider registration):

1. Call `configure_logging(settings)` to reconfigure Loguru to JSON sink when `LOG_FORMAT=json`
2. Call `setup_telemetry(app, engine, settings)` to initialize OTel SDK and instrument FastAPI + SQLAlchemy

Both calls must happen before `load_providers()` and before the first `logger.info()` call. The OTel `FastAPIInstrumentor.instrument_app(app)` must be called after `app = FastAPI(...)`.

**New import sequence in main.py:**
```python
# At top of lifespan():
from civpulse_geo.telemetry import setup_telemetry, configure_logging
configure_logging(settings)           # Reconfigure Loguru first
setup_telemetry(app, engine, settings)  # OTel second (Loguru patcher needs provider set)
# ... then existing provider registration ...
```

### `config.py` Additions

```python
# Observability settings (v1.3)
otel_enabled: bool = False           # Default off for local dev without Tempo
otel_endpoint: str = "http://localhost:4317"  # OTLP gRPC endpoint
otel_service_name: str = "civpulse-geo"
log_format: str = "text"             # "json" in K8s, "text" for local dev
```

### `api/health.py` Modifications

Add `/health/live` and `/health/ready` routes alongside the existing `/health`. No changes to existing `/health` behavior.

### `database.py` — No changes needed

The `engine` object is already a module-level `AsyncEngine`. `setup_telemetry()` receives it and accesses `engine.sync_engine` for `SQLAlchemyInstrumentor`. No changes to `database.py`.

### `providers/`, `services/`, `models/` — Unchanged

All business logic is unchanged. OTel instrumentation is transparent to application code. Loguru calls (`logger.info()`, `logger.warning()`, etc.) are unchanged — the patcher injects trace context automatically without modifying call sites.

---

## Security Context (K8s)

```yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 1001
  runAsGroup: 1001
  readOnlyRootFilesystem: true
  allowPrivilegeEscalation: false
  capabilities:
    drop: ["ALL"]
  seccompProfile:
    type: RuntimeDefault

# Writable volumes required for read-only FS:
volumes:
  - name: tmp
    emptyDir: {}

volumeMounts:
  - name: tmp
    mountPath: /tmp
```

**Why `/tmp` is needed:** Python's `tempfile` module (used by fiona for GDAL operations and by some httpx internals) writes to `/tmp`. The GDAL native library also uses `/tmp` for intermediate processing. `/gisdata/temp` from the existing Dockerfile is only needed for Tiger data import (CLI operation), not for the API runtime.

**The Ollama sidecar cannot run with readOnlyRootFilesystem=true** — Ollama requires write access to `/root/.ollama` and `/tmp`. Apply the restrictive security context only to the `geo-api` container, not the `ollama` sidecar. Use container-level `securityContext` (not pod-level) to scope the restriction.

---

## Anti-Patterns

### Anti-Pattern 1: Running Alembic Migrations in the API Lifespan

**What people do:** Call `alembic upgrade head` inside FastAPI's lifespan startup event or via a startup script embedded in the main container.

**Why it's wrong:** In K8s with multiple replicas, all pods start simultaneously and all attempt migrations concurrently. While Alembic's advisory lock prevents dual-application, the lock contention slows startup and can cause confusing pod `CrashLoopBackOff` if the migration pod errors. More critically, a failed migration should prevent the pod from starting — there is no way to fail a pod cleanly from inside the lifespan.

**Do this instead:** Use a K8s init container with the migration. If migration fails, the init container exits non-zero, the pod stays in `Init:Error` state, and ArgoCD surfaces the failure clearly. The main container never starts until migration succeeds.

### Anti-Pattern 2: OTel Provider Initialized After FastAPI App

**What people do:** Create `app = FastAPI(...)` at module level, then configure OTel in `main()` or at the bottom of the module.

**Why it's wrong:** `FastAPIInstrumentor.instrument_app(app)` must be called after `app` is created but before any routes are registered. If the TracerProvider is not set when the instrumentor hooks in, spans are created with a no-op provider and silently dropped. Module-level initialization order is fragile.

**Do this instead:** Create a `telemetry.py` module. Call `setup_telemetry()` at the start of the lifespan function. `instrument_app(app)` runs while the app is fully constructed but before it handles any requests.

### Anti-Pattern 3: Loguru serialize=True Without enqueue=True

**What people do:** Enable JSON serialization (`serialize=True`) without enabling the async-safe queue (`enqueue=True`).

**Why it's wrong:** Loguru's default sink is synchronous. In a FastAPI/uvicorn async context, synchronous logging calls can block the event loop, especially when JSON serialization is involved. This causes P99 latency spikes under load.

**Do this instead:** Always use `enqueue=True` with production sinks. This moves log serialization and writing to a background thread, keeping the event loop free.

### Anti-Pattern 4: Using `latest` Tag in ArgoCD Sync

**What people do:** Set the image tag to `latest` in K8s manifests and rely on `imagePullPolicy: Always` for updates.

**Why it's wrong:** ArgoCD compares the desired state (manifest) with the live state (cluster). If the tag is always `latest`, ArgoCD sees no manifest change and does not trigger a sync, even though the underlying image has changed. This breaks GitOps — the manifest no longer represents the actual deployed state.

**Do this instead:** Use the git commit SHA as the image tag. Every push produces a unique tag. ArgoCD detects the tag change in the manifest and syncs.

### Anti-Pattern 5: Shared SecurityContext for Ollama Sidecar

**What people do:** Apply `readOnlyRootFilesystem: true` at the pod level, which applies to all containers including the Ollama sidecar.

**Why it's wrong:** Ollama writes model files to `/root/.ollama` and uses `/tmp` heavily during inference. A read-only root filesystem will crash Ollama on startup or on first inference. The PVC provides the model storage but does not cover the runtime tmp usage.

**Do this instead:** Apply `readOnlyRootFilesystem: true` only at the container level for the `geo-api` container. Leave the `ollama` sidecar without this restriction.

---

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| Single node k3s (current) | 1 replica per namespace. No HPA needed. Ollama sidecar CPU-bound. |
| Multi-replica (prod HA) | Alembic advisory lock handles concurrent init containers. OTel BatchSpanProcessor is per-process (no shared state). Loguru enqueue is per-process. No shared state across replicas. |
| High RPS (> 100 req/s) | OTel BatchSpanProcessor default batch size (512 spans, 5s export interval) handles ~1000 req/s. Increase `max_export_batch_size` if span backlog grows. SQLAlchemy connection pool size governs DB concurrency — current default (5 connections) limits throughput. |
| Trace volume control | Set `OTEL_TRACES_SAMPLER=parentbased_traceidratio` with `OTEL_TRACES_SAMPLER_ARG=0.1` to sample 10% of traces in prod, reducing Tempo storage cost while preserving full traces for errors. |

---

## Build Order for v1.3

This order minimizes risk and keeps each phase independently deployable.

| Step | Component | Dependencies | Rationale |
|------|-----------|--------------|-----------|
| 1 | Multi-stage Dockerfile | None | Foundation for all K8s work. Validate image builds, non-root runs correctly, fiona/GDAL libs present. |
| 2 | `telemetry.py` + `config.py` additions | Dockerfile (need to test in container) | Add OTel SDK + Loguru JSON sink. Feature-flagged (`OTEL_ENABLED=false` default). No K8s needed yet. |
| 3 | `/health/live` + `/health/ready` endpoints | telemetry.py | Required by K8s probes. Test in Docker Compose first. |
| 4 | K8s base manifests (Deployment, Service, ConfigMap, Secret) | Multi-stage Dockerfile, health endpoints | Port-forward to test before ArgoCD. Use `kubectl apply` manually first. |
| 5 | Init containers (wait-for-db + alembic-migrate) | K8s manifests, external PostgreSQL access | Verify migration init container works with civpulse-infra PostgreSQL. |
| 6 | Ollama sidecar integration in Deployment | K8s manifests, ollama PVC | Validate `http://localhost:11434` connectivity from geo-api container. |
| 7 | ArgoCD Application CRs | K8s manifests in repo | Wire ArgoCD to git repo. Validate auto-sync on manifest change. |
| 8 | GitHub Actions CI/CD workflow | GHCR access, ArgoCD working | Full pipeline: test -> build -> push -> update manifest -> ArgoCD sync. |
| 9 | Observability validation | Full pipeline deployed | Verify traces appear in Tempo, logs in Loki, metrics in VictoriaMetrics. |

---

## Sources

- Codebase inspection: `src/civpulse_geo/main.py` — lifespan pattern, provider registration, `app.state.http_client` (HIGH confidence)
- Codebase inspection: `src/civpulse_geo/config.py` — existing settings structure, Pydantic BaseSettings (HIGH confidence)
- Codebase inspection: `src/civpulse_geo/api/health.py` — current single health endpoint (HIGH confidence)
- Codebase inspection: `src/civpulse_geo/database.py` — AsyncEngine, AsyncSessionLocal (HIGH confidence)
- Codebase inspection: `Dockerfile` — existing single-stage structure, fiona/GDAL deps, uv setup (HIGH confidence)
- Codebase inspection: `docker-compose.yml` — service topology, env vars, Ollama sidecar pattern (HIGH confidence)
- Codebase inspection: `k8s/ollama-deployment.yaml` — existing model-pull init container pattern (HIGH confidence)
- Codebase inspection: `scripts/docker-entrypoint.sh` — wait-for-db + migration + uvicorn exec pattern (HIGH confidence)
- [uv Docker guide](https://docs.astral.sh/uv/guides/integration/docker/) — multi-stage pattern, `UV_PYTHON_DOWNLOADS=0`, `--no-editable` (HIGH confidence)
- [Running uv containers read-only](https://slhck.info/software/2025/09/19/running-uv-docker-containers-read-only.html) — `PYTHONDONTWRITEBYTECODE`, tmpfs requirements (MEDIUM confidence)
- [OpenTelemetry Python instrumentation](https://opentelemetry.io/docs/languages/python/instrumentation/) — TracerProvider setup, BatchSpanProcessor, instrument_app ordering (HIGH confidence)
- [OpenTelemetry FastAPI instrumentation](https://pypi.org/project/opentelemetry-instrumentation-fastapi/) — v0.60b1 (Dec 2025), `FastAPIInstrumentor.instrument_app()` (HIGH confidence)
- [OpenTelemetry SQLAlchemy instrumentation](https://pypi.org/project/opentelemetry-instrumentation-sqlalchemy/) — `engine.sync_engine` for async engines (HIGH confidence)
- [Loguru GitHub](https://github.com/Delgan/loguru) — `serialize=True`, `enqueue=True`, `patcher` hook (HIGH confidence)
- [Loguru OTel trace injection](https://github.com/Delgan/loguru/issues/1222) — patcher function pattern for trace context (MEDIUM confidence — GitHub issue, not official docs)
- [Grafana Alloy Kubernetes logs](https://grafana.com/docs/alloy/latest/tutorials/send-logs-to-loki/) — `loki.source.kubernetes_logs` pod stdout collection (HIGH confidence)
- [Kubernetes init containers](https://kubernetes.io/docs/concepts/workloads/pods/init-containers/) — sequential execution, pod lifecycle (HIGH confidence)
- [K8s graceful shutdown / preStop hook](https://devopscube.com/kubernetes-pod-graceful-shutdown/) — preStop sleep pattern, exec form PID 1 requirement (MEDIUM confidence)
- [GitHub Actions GHCR push](https://github.com/marketplace/actions/build-and-publish-docker-image-to-github-container-registry) — `GITHUB_TOKEN` auth, `docker/build-push-action@v6` (HIGH confidence)
- [Hynek.me Docker uv guide](https://hynek.me/articles/docker-uv/) — non-root user, `UV_LINK_MODE=copy`, `UV_COMPILE_BYTECODE=1` (HIGH confidence)

---

*Architecture research for: CivPulse Geo API v1.3 Production Readiness & Deployment*
*Researched: 2026-03-29*
