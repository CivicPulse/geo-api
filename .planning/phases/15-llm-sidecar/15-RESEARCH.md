# Phase 15: LLM Sidecar - Research

**Researched:** 2026-03-29
**Domain:** Ollama local LLM integration, structured JSON output, Docker Compose / Kubernetes deployment, cascade pipeline extension
**Confidence:** HIGH

## Summary

Phase 15 adds a local Ollama LLM sidecar (qwen2.5:3b) as stage 4 of the cascade pipeline. The stage fires only when exact match and fuzzy stages produce zero geocode results — it sends the raw address string to the LLM, receives a structured JSON component extraction, applies hard-reject guardrails, then re-runs the corrected address through exact-match providers. The LLM never directly produces a geocode result.

The existing codebase already has all the integration points the planner needs: the cascade pipeline's stage timeout pattern (`asyncio.wait_for` with graceful fallback), the `app.state` startup pattern from `SpellCorrector`, the conditional provider registration pattern (`_oa_data_available`), and the `getattr(request.app.state, "fuzzy_matcher", None)` pattern in the API route for optional services. The LLM client follows all of these exactly.

Ollama's REST API supports structured JSON schema output via a `format` parameter on `/api/generate` or `/api/chat`. The `ollama` Python package (v0.6.1) wraps httpx with an `AsyncClient` class, but since the project already uses httpx and the structured output schema must be passed as a dict, a thin direct httpx wrapper is equally valid and avoids a new dependency. The decision is left to Claude's discretion (D-C in CONTEXT.md).

**Primary recommendation:** Use direct httpx for the Ollama client (reuses existing httpx.AsyncClient from app.state, no new dependency, full control over the 5000ms timeout), Ollama's `format` field with a JSON schema dict to constrain output, and a hardcoded zip-prefix-to-first-digit-state-group dict for the state-change guardrail.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**LLM Interaction Design (LLM-02)**
- D-01: LLM receives raw address string only — no provider failure context, no fuzzy near-misses
- D-02: LLM returns structured JSON with full component extraction: street_number, street_name, street_suffix, city, state, zip — mirrors the 5-tuple used by local providers (_parse_input_address)
- D-03: Single best correction only (not multiple variants). temperature=0 for deterministic output. One JSON object per request
- D-04: Structured JSON schema output enforced via Ollama's format parameter — model constrained to expected schema

**Cascade Integration (LLM-02, LLM-03)**
- D-05: LLM fires as stage 4 (between fuzzy and consensus) ONLY when exact + fuzzy stages produced zero geocode results
- D-06: Re-verified results only enter consensus scoring. LLM has no trust weight — re-verified results carry their normal provider trust weights (Census=0.90, OA=0.80, etc.)
- D-07: LLM stage timeout: 5000ms (generous)
- D-08: LLM timeout follows existing graceful degradation pattern (D-16 from Phase 14): if timeout hits, skip stage and continue cascade with whatever prior stages produced
- D-09: CASCADE_LLM_ENABLED env var (default: false) follows the CASCADE_ENABLED feature flag pattern from Phase 14

**Infrastructure & Deployment (LLM-01, LLM-04)**
- D-10: Docker Compose: Ollama service using ollama/ollama image, auto-pull qwen2.5:3b on first start via entrypoint script. Volume for model persistence
- D-11: Resource limits: mem_limit: 4g only, no CPU limit. qwen2.5:3b uses ~2-3GB RAM
- D-12: K8s manifests: CPU-only Deployment + PVC for model storage. No GPU requirements. ArgoCD-compatible (plain manifests or Kustomize)
- D-13: Health check: Ollama exposes GET /api/tags — use as readiness probe. Model availability checked at API startup

**Safety Guardrails (LLM-03)**
- D-14: Hard-reject before re-verification: reject if LLM changed the state code from original input, or if LLM's zip doesn't match the state (basic zip-prefix-to-state mapping)
- D-15: When Ollama unavailable: silent skip — log warning, skip LLM stage, cascade continues with deterministic results
- D-16: Malformed JSON (parse failure, missing required fields): no retry, skip stage
- D-17: LLM output is NEVER used as a geocode result directly — the corrected address is re-run through exact-match providers

### Claude's Discretion
- LLMAddressCorrector class structure and method decomposition
- Exact prompt engineering for qwen2.5:3b (system prompt, few-shot examples)
- Ollama client implementation (httpx async client vs ollama-python library)
- Zip-prefix-to-state mapping implementation (hardcoded dict vs database lookup)
- How re-verification calls providers (reuse existing exact-match stage logic vs dedicated re-verify method)
- K8s manifest format (plain YAML vs Kustomize overlays)
- Ollama Docker entrypoint script details (pull retry logic, startup ordering)
- cascade_trace fields for the LLM stage
- set_by_stage value for LLM-assisted results (e.g., "llm_correction_consensus")

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| LLM-01 | Ollama + qwen2.5:3b Docker Compose service added, feature-flagged off by default (CASCADE_LLM_ENABLED=false) | Ollama Docker Compose pattern documented; entrypoint script auto-pull pattern verified |
| LLM-02 | LLMAddressCorrector sends address to local LLM with structured JSON schema output (temperature=0) for component extraction and correction | Ollama format parameter with JSON schema dict verified; qwen2.5:3b structured output quality confirmed |
| LLM-03 | Every LLM-corrected address is re-verified against provider databases before use — LLM output never used as geocode result directly | Re-verification pattern documented; guardrail logic (state change + zip mismatch) researched |
| LLM-04 | K8s manifests for Ollama deployment with PVC for model storage (ArgoCD-compatible) | K8s Deployment + PVC patterns documented; CPU-only resource specifications identified |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

No CLAUDE.md exists in the project root. Project conventions are established by the existing codebase patterns documented below.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| ollama/ollama | latest Docker image | Local LLM server | Official image; exposes REST API at :11434 |
| qwen2.5:3b | Q4_K_M quantization | Address correction LLM | 1.9GB, ~2-3GB RAM, strong structured JSON output, CPU viable |
| httpx | >=0.28.1 (already in deps) | Async HTTP client for Ollama API | Already in project; thin wrapper around Ollama REST API avoids new dependency |
| pydantic | (already in deps via fastapi) | JSON schema generation + response validation | Schema defined as Pydantic model, .model_json_schema() generates the format dict |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| ollama (PyPI) | 0.6.1 | Official Python wrapper around Ollama API | Alternative to direct httpx; adds typed responses and AsyncClient |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Direct httpx | ollama-python 0.6.1 | ollama-python adds typed responses; httpx gives full control of timeout, reuses existing client from app.state |
| Hardcoded zip-prefix dict | uszipcode/zipcodes library | Libraries have more data but add a dependency; 3-digit prefix to state mapping can be inlined (first-digit gives state group) |

**Installation (if ollama-python chosen):**
```bash
uv add ollama
```

**If httpx-direct (recommended — no new dependency):** No install needed.

**Version verification:**
```bash
# ollama-python if used
uv run python -c "import ollama; print(ollama.__version__)"
# Current verified: 0.6.1 (PyPI, 2025-11-13)
```

## Architecture Patterns

### Recommended Project Structure
```
src/civpulse_geo/
├── services/
│   ├── cascade.py          # MODIFY: insert LLM stage between fuzzy and consensus
│   ├── llm_corrector.py    # NEW: LLMAddressCorrector class
│   └── geocoding.py        # MODIFY: thread llm_corrector into cascade.run()
├── config.py               # MODIFY: add CASCADE_LLM_ENABLED, OLLAMA_URL, LLM_TIMEOUT_MS
├── main.py                 # MODIFY: LLM client init into app.state at startup
scripts/
├── ollama-entrypoint.sh    # NEW: auto-pull script for Docker Compose
docker-compose.yml          # MODIFY: add ollama service
k8s/
├── ollama-deployment.yaml  # NEW: K8s Deployment
├── ollama-pvc.yaml         # NEW: PersistentVolumeClaim
└── ollama-service.yaml     # NEW: K8s Service
tests/
└── test_llm_corrector.py   # NEW: unit tests for LLMAddressCorrector
```

### Pattern 1: LLMAddressCorrector Class

**What:** A standalone service class (stateless, instantiated per-request or stored in app.state) that wraps Ollama API calls. Mirrors the SpellCorrector pattern but async.

**When to use:** Called from CascadeOrchestrator.run() when `not skip_fuzzy and len(candidates) == 0` after the fuzzy stage.

**Example (httpx-direct approach):**
```python
# Source: Ollama API docs https://docs.ollama.com/capabilities/structured-outputs
import json
import httpx
from pydantic import BaseModel

class AddressCorrection(BaseModel):
    street_number: str | None
    street_name: str | None
    street_suffix: str | None
    city: str | None
    state: str | None
    zip: str | None

class LLMAddressCorrector:
    def __init__(self, ollama_url: str, model: str = "qwen2.5:3b") -> None:
        self._ollama_url = ollama_url
        self._model = model
        self._schema = AddressCorrection.model_json_schema()

    async def correct_address(
        self,
        raw_address: str,
        http_client: httpx.AsyncClient,
    ) -> AddressCorrection | None:
        """Send raw address to LLM; return structured correction or None on failure."""
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": raw_address},
            ],
            "stream": False,
            "format": self._schema,
            "options": {"temperature": 0},
        }
        try:
            resp = await http_client.post(
                f"{self._ollama_url}/api/chat",
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["message"]["content"]
            return AddressCorrection.model_validate_json(content)
        except Exception as exc:
            logger.warning("LLMAddressCorrector: failed — {}", exc)
            return None
```

### Pattern 2: Cascade Stage 4 (LLM) Insertion

**What:** New stage in `CascadeOrchestrator.run()` between fuzzy (stage 3) and consensus (stage 4 → now stage 5). Fires only when `len(candidates) == 0` after fuzzy.

**When to use:** Always — but gated by `CASCADE_LLM_ENABLED` and `llm_corrector is not None`.

**Example:**
```python
# Source: existing cascade.py timeout pattern (D-16 from Phase 14)
# After Stage 3 (fuzzy), before consensus:

if (
    settings.cascade_llm_enabled
    and llm_corrector is not None
    and len(candidates) == 0  # D-05: only fires when all deterministic stages failed
):
    t_stage = time.monotonic()
    try:
        correction = await asyncio.wait_for(
            llm_corrector.correct_address(freeform, http_client),
            timeout=settings.llm_timeout_ms / 1000,  # D-07: 5000ms
        )
        if correction is not None and _passes_guardrails(correction, freeform):
            # Re-run exact match with corrected address components
            corrected_str = _correction_to_address_string(correction)
            # ... call providers in parallel with corrected_str ...
    except asyncio.TimeoutError:
        logger.warning("LLM stage timed out after {}ms", settings.llm_timeout_ms)
        # D-08: timeout degrades gracefully — cascade continues with empty candidates
```

### Pattern 3: app.state Startup (LLM Client)

**What:** Initialize LLM client availability at startup using the same conditional pattern as `_oa_data_available` and `SpellCorrector`.

**Example:**
```python
# Source: existing main.py lifespan pattern
# In lifespan() after other providers:

app.state.llm_corrector = None
if settings.cascade_llm_enabled:
    try:
        available = await _ollama_model_available(
            settings.ollama_url,
            app.state.http_client,
            "qwen2.5:3b",
        )
        if available:
            app.state.llm_corrector = LLMAddressCorrector(
                ollama_url=settings.ollama_url
            )
            logger.info("LLM corrector registered (qwen2.5:3b)")
        else:
            logger.warning("Ollama model qwen2.5:3b not available — LLM stage disabled")
    except Exception as e:
        logger.warning("LLM corrector not loaded: {}", e)
```

### Pattern 4: Ollama Availability Check

**What:** Check `GET /api/tags` at startup to verify the model was pulled successfully.

**Example:**
```python
async def _ollama_model_available(
    ollama_url: str,
    http_client: httpx.AsyncClient,
    model_name: str,
) -> bool:
    """Check Ollama is running and model is available. Returns False on any error."""
    try:
        resp = await http_client.get(f"{ollama_url}/api/tags", timeout=5.0)
        resp.raise_for_status()
        models = resp.json().get("models", [])
        return any(m["name"].startswith(model_name) for m in models)
    except Exception:
        return False
```

### Pattern 5: Docker Compose Ollama Service

**What:** Third service in docker-compose.yml with volume persistence, entrypoint auto-pull, and health check.

**Example:**
```yaml
# Source: heyvaldemar/ollama-traefik-letsencrypt-docker-compose pattern (verified 2025)
  ollama:
    image: ollama/ollama:latest
    entrypoint: ["/bin/bash", "/entrypoint.sh"]
    environment:
      - OLLAMA_MODELS=qwen2.5:3b
    volumes:
      - ollama_data:/root/.ollama
      - ./scripts/ollama-entrypoint.sh:/entrypoint.sh:ro
    mem_limit: 4g
    ports:
      - "11434:11434"
    healthcheck:
      test: ["CMD-SHELL", "curl -sf http://localhost:11434/api/tags || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 10
      start_period: 120s   # model pull can take time on first start

volumes:
  ollama_data:
```

**Entrypoint script pattern (scripts/ollama-entrypoint.sh):**
```bash
#!/bin/bash
set -euo pipefail

# Start Ollama server in background
/bin/ollama serve &
OLLAMA_PID=$!

# Wait for server to be ready
echo "Waiting for Ollama server..."
until curl -sf http://localhost:11434/api/tags > /dev/null 2>&1; do
  sleep 2
done
echo "Ollama server ready."

# Pull model (idempotent — skip if already cached in volume)
for MODEL in ${OLLAMA_MODELS//,/ }; do
  echo "Pulling model: $MODEL"
  ollama pull "$MODEL"
done

echo "Model(s) ready. Ollama serving."
wait $OLLAMA_PID
```

**Key detail:** `ollama pull` is idempotent — if the model is already in the volume, it returns immediately. The volume (`ollama_data`) persists across container restarts so the 1.9GB download only happens once.

### Pattern 6: Kubernetes Manifests (LLM-04)

**What:** Plain YAML manifests in `k8s/` directory. ArgoCD detects these automatically via path.

**Deployment:**
```yaml
# k8s/ollama-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ollama
spec:
  replicas: 1
  selector:
    matchLabels:
      app: ollama
  template:
    metadata:
      labels:
        app: ollama
    spec:
      containers:
      - name: ollama
        image: ollama/ollama:latest
        ports:
        - containerPort: 11434
        resources:
          requests:
            memory: "2Gi"
            cpu: "1"
          limits:
            memory: "4Gi"
            # no CPU limit per D-11
        volumeMounts:
        - name: ollama-data
          mountPath: /root/.ollama
        readinessProbe:
          httpGet:
            path: /api/tags
            port: 11434
          initialDelaySeconds: 30
          periodSeconds: 10
          failureThreshold: 12  # 2 minutes for first model pull
      volumes:
      - name: ollama-data
        persistentVolumeClaim:
          claimName: ollama-pvc
```

**PVC:**
```yaml
# k8s/ollama-pvc.yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: ollama-pvc
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 10Gi  # qwen2.5:3b is 1.9GB; 10Gi leaves room
```

**Service:**
```yaml
# k8s/ollama-service.yaml
apiVersion: v1
kind: Service
metadata:
  name: ollama
spec:
  selector:
    app: ollama
  ports:
  - port: 11434
    targetPort: 11434
  type: ClusterIP
```

### Pattern 7: Safety Guardrails

**What:** Hard-reject function that inspects the LLM correction before re-verification.

**Key logic (D-14):**
```python
# Hardcoded first-digit to state group mapping (conservative — only rejects clear mismatches)
# Source: USPS ZIP code geography (US ZIP Code first digit assignment)
_ZIP_FIRST_DIGIT_STATES = {
    "0": {"CT", "MA", "ME", "NH", "NJ", "PR", "RI", "VT", "VI"},
    "1": {"DE", "NY", "PA"},
    "2": {"DC", "MD", "NC", "SC", "VA", "WV"},
    "3": {"AL", "FL", "GA", "MS", "TN"},
    "4": {"IN", "KY", "MI", "OH"},
    "5": {"IA", "MN", "MT", "ND", "SD", "WI"},
    "6": {"IL", "KS", "MO", "NE"},
    "7": {"AR", "LA", "OK", "TX"},
    "8": {"AZ", "CO", "ID", "NM", "NV", "UT", "WY"},
    "9": {"AK", "AS", "CA", "GU", "HI"},
}

def _passes_guardrails(
    correction: AddressCorrection,
    original_freeform: str,
    original_state: str | None,
) -> bool:
    """Return False if LLM correction should be hard-rejected (D-14)."""
    # Reject if LLM changed the state code
    if original_state and correction.state:
        if correction.state.upper() != original_state.upper():
            return False

    # Reject if LLM zip first digit doesn't match corrected state
    if correction.zip and correction.state and len(correction.zip) >= 1:
        first_digit = correction.zip[0]
        allowed_states = _ZIP_FIRST_DIGIT_STATES.get(first_digit, set())
        if allowed_states and correction.state.upper() not in allowed_states:
            return False

    return True
```

**Important caveat:** First-digit zip-to-state mapping is approximate. Some 3-digit SCF areas cross state lines. The guardrail uses only the first digit to reject obvious state/zip mismatches (e.g., a GA address with a 9xxxx California zip). False positives where a valid cross-border zip is rejected are acceptable trade-offs given D-14's design goal.

### Anti-Patterns to Avoid

- **LLM result used as geocode directly:** Never add `AddressCorrection` as a `ProviderCandidate`. Only add candidates from re-verification provider calls (D-17).
- **LLM fires on partial matches:** The `len(candidates) == 0` gate is mandatory. If fuzzy found anything, skip LLM entirely (D-05).
- **Retry on JSON parse failure:** `temperature=0` plus schema enforcement means retrying the same input produces the same bad output. Log and skip (D-16).
- **Separate httpx.AsyncClient for Ollama:** Reuse the existing `http_client` from `app.state`. The 5000ms timeout is enforced by `asyncio.wait_for`, not httpx timeout config.
- **LLM client stored per-request:** LLMAddressCorrector should live in `app.state` (initialized once at startup), not instantiated per-request.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Structured JSON schema | Manual string templates | Pydantic `.model_json_schema()` + Ollama `format` param | Ollama enforces the schema at the model level; no post-hoc parsing needed |
| LLM API client | Custom HTTP wrapper with retry | Direct httpx (thin, already present) or ollama 0.6.1 | Ollama REST API is simple; 3 fields in the request body |
| Model pull on startup | Polling /api/tags in app startup | Docker entrypoint script pulls model before container is healthy | Cleaner separation: infra guarantees model is available before app connects |
| Zip-to-state validation | External API call | Hardcoded first-digit dict | Fast, offline, no dependency; sufficient for catching obvious LLM hallucinations |

**Key insight:** The LLM is plumbing, not logic. Keep the LLMAddressCorrector class small (one async method), and put all cascade logic in the orchestrator where it belongs.

## Common Pitfalls

### Pitfall 1: LLM Stage Fires on Empty Fuzzy (Zero Candidates vs. Zero Results)

**What goes wrong:** The LLM fires even when exact match produced results but fuzzy added nothing, because `len(candidates) == 0` is checked after the wrong point.

**Why it happens:** Candidates accumulate across stages. After exact match, `candidates` may already have entries. The LLM gate must check `len(candidates) == 0` **after both exact match and fuzzy** stages complete.

**How to avoid:** Place the LLM trigger block immediately after the fuzzy stage block ends, checking the same `candidates` list that has been built up across both stages.

**Warning signs:** LLM fires for addresses that exact match successfully.

### Pitfall 2: Re-Verification Passes All Providers Regardless of Feature Availability

**What goes wrong:** Re-verification calls providers that may not be registered (e.g., OA data not loaded, Tiger extension absent).

**Why it happens:** Re-verification uses `providers` dict from `CascadeOrchestrator.run()` which already contains only registered providers. This is actually the correct approach — reuse the same `providers` dict.

**How to avoid:** Re-use the exact same parallel `_call_provider` pattern from Stage 2 (exact match) but with the corrected address string. No special handling needed.

### Pitfall 3: Ollama Container Start Race — API Connects Before Model Is Pulled

**What goes wrong:** `CASCADE_LLM_ENABLED=true`, Ollama container starts, API starts, `_ollama_model_available()` returns False (model still pulling), LLM corrector stays None. Even after model finishes pulling, the corrector stays None until next restart.

**Why it happens:** App startup availability check runs once. Model pull runs asynchronously in the container entrypoint.

**How to avoid:** For Docker Compose, the Ollama service health check (`start_period: 120s`) ensures the API service's `depends_on` with `condition: service_healthy` doesn't complete until Ollama reports healthy AND the model is pulled. The `_ollama_model_available()` check at startup is a secondary validation.

**Warning signs:** LLM corrector is `None` despite `CASCADE_LLM_ENABLED=true`.

### Pitfall 4: cascade.py Stage Numbering Comment Drift

**What goes wrong:** The docstring at the top of `cascade.py` documents "Stages: normalize → spell-correct → exact match → fuzzy → consensus → auto-set" — adding LLM between fuzzy and consensus changes this but the comment won't auto-update.

**How to avoid:** Include comment update in the cascade.py modification task.

### Pitfall 5: `set_by_stage` Logic Does Not Account for LLM-Assisted Results

**What goes wrong:** Existing `set_by_stage` logic in consensus uses `any(m.is_fuzzy ...)` check. LLM-corrected candidates re-verified by providers are NOT fuzzy — they are normal provider candidates. They need their own set_by_stage value to trace the source.

**How to avoid:** Add a new `is_llm_corrected: bool` field to `ProviderCandidate` (similar to `is_fuzzy`). Check for it in the `set_by_stage` determination block. Suggested value: `"llm_correction_consensus"`.

### Pitfall 6: Malformed LLM JSON with Partial Schema Compliance

**What goes wrong:** Ollama's schema enforcement is best-effort for small models. qwen2.5:3b may occasionally return a valid JSON object with unexpected field names or wrong types.

**Why it happens:** Temperature=0 + schema enforcement is strong but not a hard guarantee for 3B models under CPU constraints.

**How to avoid:** Use `AddressCorrection.model_validate_json(content)` with a try/except. Pydantic validation catches type mismatches and missing required fields. Log the raw response on parse failure for debugging (D-16).

### Pitfall 7: httpx Timeout vs asyncio.wait_for Timeout

**What goes wrong:** httpx.AsyncClient has its own timeout (`timeout=10.0` set in `main.py`). A 5000ms `asyncio.wait_for` wrapping a call with a 10s httpx timeout may not cancel the httpx request promptly.

**How to avoid:** Either (a) pass `timeout=5.5` explicitly on the httpx POST call inside `correct_address()` to let httpx cancel the request cleanly, or (b) rely on `asyncio.wait_for` which cancels the coroutine regardless. Option (a) is cleaner for resource hygiene.

## Code Examples

Verified patterns from official sources:

### Ollama Structured Output Request (POST /api/chat)
```python
# Source: https://docs.ollama.com/capabilities/structured-outputs
payload = {
    "model": "qwen2.5:3b",
    "messages": [
        {"role": "system", "content": "You are an address parsing assistant..."},
        {"role": "user", "content": "123 Main St, Macon GA 31201"},
    ],
    "stream": False,
    "format": {
        "type": "object",
        "properties": {
            "street_number": {"type": ["string", "null"]},
            "street_name": {"type": ["string", "null"]},
            "street_suffix": {"type": ["string", "null"]},
            "city": {"type": ["string", "null"]},
            "state": {"type": ["string", "null"]},
            "zip": {"type": ["string", "null"]},
        },
        "required": ["street_number", "street_name", "street_suffix", "city", "state", "zip"],
    },
    "options": {"temperature": 0},
}
```

### Pydantic Schema Generation for format Dict
```python
from pydantic import BaseModel

class AddressCorrection(BaseModel):
    street_number: str | None = None
    street_name: str | None = None
    street_suffix: str | None = None
    city: str | None = None
    state: str | None = None
    zip: str | None = None

# Pass directly as the format parameter:
schema = AddressCorrection.model_json_schema()
```

### asyncio.wait_for with Graceful Degradation (existing pattern in cascade.py)
```python
# Source: existing cascade.py Stage 3 fuzzy match timeout pattern
try:
    result = await asyncio.wait_for(
        llm_corrector.correct_address(freeform, http_client),
        timeout=settings.llm_timeout_ms / 1000,
    )
except asyncio.TimeoutError:
    logger.warning(
        "CascadeOrchestrator: LLM stage timed out after {}ms",
        settings.llm_timeout_ms,
    )
    if trace or dry_run:
        cascade_trace.append({
            "stage": "llm_correction",
            "timeout": True,
            "ms": settings.llm_timeout_ms,
        })
```

### Config Addition (pydantic_settings pattern)
```python
# Source: existing config.py pattern
# CASCADE_LLM_ENABLED env var (D-09) — default False
cascade_llm_enabled: bool = False
ollama_url: str = "http://ollama:11434"
llm_timeout_ms: int = 5000
```

### GET /api/tags Health Check Response Format
```json
{
  "models": [
    {
      "name": "qwen2.5:3b",
      "model": "qwen2.5:3b",
      "modified_at": "2025-03-19T...",
      "size": 1900000000,
      "details": {"family": "qwen2", "parameter_size": "3B", "quantization_level": "Q4_K_M"}
    }
  ]
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Ollama format="json" (unstructured) | format={JSON schema dict} (structured outputs) | Ollama v0.4.7 (late 2024) | Model is constrained to exact schema; no post-hoc field extraction needed |
| ollama pull requires running server | ollama pull in entrypoint after `ollama serve &` | 2024 onward | Pull and serve are separate operations; entrypoint script pattern is now standard |
| Dockerfile-based custom image for model pull | Volume + entrypoint.sh on standard image | 2025 community pattern | Simpler: no custom Docker image, volume provides persistence |

**Deprecated/outdated:**
- `format: "json"`: Forces JSON output but does not enforce schema. Use the schema dict form instead for LLM-02 compliance.

## Open Questions

1. **Prompt quality for qwen2.5:3b on address correction**
   - What we know: qwen2.5:3b has strong structured output and instruction following; temperature=0 + schema enforcement is reliable
   - What's unclear: Few-shot examples help small models significantly; the exact prompt engineering is left to Claude's discretion
   - Recommendation: Include 2-3 few-shot examples in the system prompt: one clean address, one with abbreviated street suffix, one with transposed city/state. Log the raw LLM response in DEBUG mode during first rollout to validate quality.

2. **Re-verification: reuse _call_provider or dedicated re-verify method**
   - What we know: The existing `_call_provider` closure in `cascade.py` Stage 2 calls `provider.geocode(normalized, http_client=http_client)` — re-verification needs `provider.geocode(corrected_str, ...)` with a different address string
   - What's unclear: Whether inline logic (copy the parallel gather pattern with corrected_str) or a refactored helper is cleaner
   - Recommendation: Inline copy of the gather pattern for Stage 4 re-verification. It keeps the stage self-contained and avoids refactoring Stage 2 which is working correctly.

3. **K8s model initialization on first deploy**
   - What we know: The K8s Deployment doesn't have an auto-pull entrypoint; the pod will start with no model
   - What's unclear: Whether an init container or a modified entrypoint should handle the first pull
   - Recommendation: Add an `initContainer` to the K8s Deployment that runs `ollama pull qwen2.5:3b`. Init containers share the PVC volume and run before the main container, providing the same "model ready before serving" guarantee as the Docker Compose entrypoint.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Docker | Docker Compose (LLM-01) | Yes | 29.3.1 | — |
| Ollama binary/image | LLM-01, LLM-04 | No (not installed locally) | — | Docker Compose provides via ollama/ollama image |
| Python 3.12 | LLMAddressCorrector (Python) | Yes | 3.12.3 | — |
| uv | Dependency management | Yes | 0.10.9 | — |
| kubectl/K8s | LLM-04 (K8s manifests) | Not tested locally | — | Manifests are YAML files; K8s on thor applied separately |

**Missing dependencies with no fallback:**
- None that block local development or testing. LLM-01 Docker Compose service only activates when `CASCADE_LLM_ENABLED=true`.

**Missing dependencies with fallback:**
- Ollama not installed locally: ollama/ollama Docker image provides the service. LLMAddressCorrector tests can be mocked (Ollama API is a simple HTTP call).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 + pytest-asyncio 1.3.0 |
| Config file | `pyproject.toml` (`[tool.pytest.ini_options]`) |
| Quick run command | `uv run pytest tests/test_llm_corrector.py -x -q` |
| Full suite command | `uv run pytest tests/ -x -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| LLM-01 | CASCADE_LLM_ENABLED=false disables LLM stage | unit | `uv run pytest tests/test_llm_corrector.py::test_llm_disabled_when_flag_false -x` | No — Wave 0 |
| LLM-01 | Ollama service unavailable → graceful skip | unit | `uv run pytest tests/test_llm_corrector.py::test_ollama_unavailable_skips_gracefully -x` | No — Wave 0 |
| LLM-02 | LLMAddressCorrector sends raw address, gets structured JSON | unit (mock HTTP) | `uv run pytest tests/test_llm_corrector.py::test_corrector_returns_structured_result -x` | No — Wave 0 |
| LLM-02 | temperature=0 and schema format parameter are sent | unit (mock HTTP) | `uv run pytest tests/test_llm_corrector.py::test_corrector_request_payload_shape -x` | No — Wave 0 |
| LLM-03 | LLM correction that changes state code is hard-rejected | unit | `uv run pytest tests/test_llm_corrector.py::test_guardrail_rejects_state_change -x` | No — Wave 0 |
| LLM-03 | LLM correction with zip/state mismatch is hard-rejected | unit | `uv run pytest tests/test_llm_corrector.py::test_guardrail_rejects_zip_state_mismatch -x` | No — Wave 0 |
| LLM-03 | Malformed JSON response skips stage (no retry) | unit | `uv run pytest tests/test_llm_corrector.py::test_malformed_json_skips_stage -x` | No — Wave 0 |
| LLM-03 | LLM correction passing guardrails re-verified via providers | unit (mock) | `uv run pytest tests/test_llm_corrector.py::test_correction_triggers_reverification -x` | No — Wave 0 |
| LLM-03 | LLM result never used as geocode result directly | unit | `uv run pytest tests/test_cascade.py::test_llm_correction_enters_reverify_not_candidates -x` | No — Wave 0 |
| LLM-04 | K8s manifests are valid YAML | smoke | `python3 -c "import yaml; [yaml.safe_load(open(f)) for f in ['k8s/ollama-deployment.yaml','k8s/ollama-pvc.yaml','k8s/ollama-service.yaml']]"` | No — Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_llm_corrector.py -x -q`
- **Per wave merge:** `uv run pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_llm_corrector.py` — covers LLM-01, LLM-02, LLM-03
- [ ] `tests/conftest.py` — add `mock_ollama_client` fixture (AsyncMock of httpx.AsyncClient.post returning a canned Ollama response)
- [ ] No new framework installs needed — pytest + pytest-asyncio already present

## Sources

### Primary (HIGH confidence)
- [Ollama Structured Outputs docs](https://docs.ollama.com/capabilities/structured-outputs) — format parameter, JSON schema shape, temperature recommendation
- [Ollama API reference (GitHub)](https://github.com/ollama/ollama/blob/main/docs/api.md) — /api/generate and /api/chat parameters, stream:false behavior
- [Ollama /api/tags response](https://docs.ollama.com/api/tags) — health check endpoint format, model name field
- Existing codebase: `cascade.py`, `main.py`, `spell/corrector.py`, `config.py` — all patterns read directly from source

### Secondary (MEDIUM confidence)
- [qwen2.5:3b Ollama library page](https://ollama.com/library/qwen2.5:3b) — 1.9GB size, Q4_K_M quantization, JSON output strengths confirmed
- [heyvaldemar entrypoint.sh pattern](https://github.com/heyvaldemar/ollama-traefik-letsencrypt-docker-compose/blob/main/entrypoint.sh) — TCP wait loop, `ollama pull` in loop, `wait $pid` process management
- [Collabnix K8s Ollama guide](https://collabnix.com/getting-started-with-ollama-on-kubernetes/) — CPU-only resource specs, port 11434, volume mount at /root/.ollama
- USPS ZIP code first-digit geography (Wikipedia / USPS) — first-digit to state group mapping for guardrail

### Tertiary (LOW confidence)
- Community reports on qwen2.5:3b address parsing quality — no formal benchmark found; structured output quality inferred from general instruction-following benchmarks

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — Ollama API verified via official docs; httpx already in project; qwen2.5:3b size/capabilities verified on ollama.com
- Architecture: HIGH — All patterns read directly from existing source files (cascade.py, main.py, corrector.py)
- Pitfalls: MEDIUM — Timeout interaction and schema enforcement edge cases are empirically reasonable but not formally verified for qwen2.5:3b specifically

**Research date:** 2026-03-29
**Valid until:** 2026-04-29 (Ollama API is stable; Docker patterns are stable)
