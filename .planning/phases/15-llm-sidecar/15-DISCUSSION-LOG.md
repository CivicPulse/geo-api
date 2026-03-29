# Phase 15: LLM Sidecar - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-29
**Phase:** 15-llm-sidecar
**Areas discussed:** LLM interaction design, Cascade integration, Infrastructure & deployment, Safety guardrails

---

## LLM Interaction Design

### LLM Input Context

| Option | Description | Selected |
|--------|-------------|----------|
| Raw address only | Send just the failed address string. Simplest prompt, fastest inference | ✓ |
| Address + failed providers | Include which providers were tried and failed | |
| Address + nearby candidates | Include top fuzzy/phonetic near-misses from stage 3 | |

**User's choice:** Raw address only
**Notes:** None

### LLM Output Format

| Option | Description | Selected |
|--------|-------------|----------|
| Full component extraction | JSON with street_number, street_name, street_suffix, city, state, zip | ✓ |
| Corrected full address string | Single corrected address string re-parsed by scourgify | |
| Components + confidence | Same as full extraction plus per-field confidence scores | |

**User's choice:** Full component extraction
**Notes:** None

### Correction Variants

| Option | Description | Selected |
|--------|-------------|----------|
| Single best correction | One JSON object, temperature=0, deterministic | ✓ |
| Up to 3 ranked variants | Array of corrections, needs temperature>0, 3x re-verification cost | |

**User's choice:** Single best correction
**Notes:** None

---

## Cascade Integration

### LLM Trigger Condition

| Option | Description | Selected |
|--------|-------------|----------|
| No results at all | LLM fires only when exact + fuzzy produced zero results | ✓ |
| No high-confidence results | LLM fires when no result has confidence >= 0.80 | |
| Always (when enabled) | LLM always runs regardless of prior results | |

**User's choice:** No results at all
**Notes:** Most conservative — LLM is truly a last resort

### Consensus Integration

| Option | Description | Selected |
|--------|-------------|----------|
| Re-verified results only | LLM correction re-run through providers; only provider results enter consensus | ✓ |
| LLM as pseudo-provider | Give LLM its own trust weight alongside re-verified results | |
| Bypass consensus entirely | Auto-set directly if re-verification confirms | |

**User's choice:** Re-verified results only
**Notes:** LLM has no trust weight — it just fixes the input

### LLM Timeout Budget

| Option | Description | Selected |
|--------|-------------|----------|
| 2000ms | Same as exact-match stage | |
| 1000ms (tight) | May cause frequent timeouts on CPU | |
| 5000ms (generous) | Accommodates CPU inference under load | ✓ |

**User's choice:** 5000ms (generous)
**Notes:** Since LLM only fires on zero results, extra latency is acceptable — the alternative is NO_MATCH

---

## Infrastructure & Deployment

### Model Provisioning

| Option | Description | Selected |
|--------|-------------|----------|
| Auto-pull on first start | Entrypoint script runs ollama pull, volume for persistence | ✓ |
| Pre-baked custom image | Dockerfile extends ollama/ollama with model baked in | |
| Volume mount from host | Mount host directory with pre-downloaded model | |

**User's choice:** Auto-pull on first start
**Notes:** None

### K8s Deployment

| Option | Description | Selected |
|--------|-------------|----------|
| CPU-only pod + PVC | Standard Deployment, no GPU requirements | ✓ |
| GPU-enabled pod + PVC | nvidia.com/gpu resource requests | |
| Defer K8s to v1.3 | Ship Docker Compose only for now | |

**User's choice:** CPU-only pod + PVC
**Notes:** Matches bare-metal K8s on thor

### Resource Limits

| Option | Description | Selected |
|--------|-------------|----------|
| Memory limit only | mem_limit: 4g, no CPU limit | ✓ |
| Memory + CPU limits | mem_limit: 4g + cpus: 2.0 | |
| No limits | Let Docker manage | |

**User's choice:** Memory limit only
**Notes:** None

---

## Safety Guardrails

### Hard-Reject Rules

| Option | Description | Selected |
|--------|-------------|----------|
| State change + zip mismatch | Reject if LLM changed state or zip doesn't match state | ✓ |
| State + zip + city plausibility | Same plus city-zip lookup table | |
| Minimal — just re-verify | Skip hard-reject, rely on provider re-verification | |

**User's choice:** State change + zip mismatch
**Notes:** None

### Ollama Unavailability

| Option | Description | Selected |
|--------|-------------|----------|
| Silent skip | Log warning, skip stage, cascade continues | ✓ |
| Return degraded flag | Same plus llm_unavailable flag in trace | |
| Retry once then skip | One retry with backoff | |

**User's choice:** Silent skip
**Notes:** Caller never knows LLM was attempted

### Malformed JSON Handling

| Option | Description | Selected |
|--------|-------------|----------|
| No retry, skip stage | Log raw response, skip | ✓ |
| One retry with reminder | Retry with "respond with valid JSON" instruction | |

**User's choice:** No retry, skip stage
**Notes:** With temperature=0 and structured output, retrying produces the same bad output

---

## Claude's Discretion

- LLMAddressCorrector class structure
- Prompt engineering for qwen2.5:3b
- Ollama client implementation choice
- Zip-prefix-to-state mapping implementation
- Re-verification method design
- K8s manifest format
- Entrypoint script details
- cascade_trace fields for LLM stage
- set_by_stage value naming

## Deferred Ideas

None
