# Architecture Research

**Domain:** CivPulse Geo API — v1.2 Cascading Address Resolution
**Researched:** 2026-03-29
**Confidence:** HIGH — based on direct codebase inspection, verified PostGIS/pg_trgm official docs, and Ollama Docker documentation

---

## v1.2 Milestone: Cascading Resolution Pipeline

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
