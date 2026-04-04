# Phase 22: Observability - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-30
**Phase:** 22-observability
**Areas discussed:** Log format switching, Metrics scope, Manual span coverage, Request-ID source

---

## Log Format Switching

| Option | Description | Selected |
|--------|-------------|----------|
| Env-based switching | JSON when ENVIRONMENT != 'local', human-readable when ENVIRONMENT == 'local'. Simple, no extra config needed. | ✓ |
| Explicit LOG_FORMAT env var | Separate LOG_FORMAT=json\|text env var for full control. More flexible but another config knob. | |
| JSON everywhere | Always output JSON, even locally. Simpler code, but less pleasant dev experience. | |

**User's choice:** Env-based switching (Recommended)
**Notes:** Uses `log_format: auto|json|text` with auto as default. K8s ConfigMap already sets ENVIRONMENT — no new config needed.

---

## Metrics Scope

| Option | Description | Selected |
|--------|-------------|----------|
| Tier 1 + 2 | Standard HTTP metrics plus provider/cascade/cache metrics. | |
| Tier 1 only | Just HTTP request rate, latency, and in-progress gauge. | |
| All three tiers | Full instrumentation including LLM correction tracking. | ✓ |
| Tier 1 + 2 + partial Tier 3 | Standard + service-specific + LLM duration only. | |

**User's choice:** All three tiers
**Notes:** Full instrumentation from day one — HTTP standard, provider/cascade/cache, and LLM/batch business metrics.

---

## Manual Span Coverage

| Option | Description | Selected |
|--------|-------------|----------|
| Cascade stages + providers | Manual spans for each cascade stage and each provider.geocode() call. | ✓ |
| Auto-instrumentation only | Rely on FastAPI, SQLAlchemy, and httpx auto-instrumentation only. | |
| Cascade stages only | Manual spans at stage boundaries but not individual provider calls. | |
| Everything including LLM | Cascade stages + providers + explicit LLM correction spans with token count attributes. | |

**User's choice:** Cascade stages + providers (Recommended)
**Notes:** Gives full waterfall in Tempo. Cascade already has timing code at stage boundaries — spans added alongside.

---

## Request-ID Source

| Option | Description | Selected |
|--------|-------------|----------|
| Accept or generate | Check X-Request-ID header, use if present, generate UUID4 if not. | ✓ |
| Always generate | Ignore incoming header, always generate fresh UUID4. | |
| Accept, validate, or generate | Accept if UUID format, reject malformed, generate if missing. | |

**User's choice:** Accept or generate (Recommended)
**Notes:** Supports future CivPulse service-to-service correlation. Returns X-Request-ID on response header.

---

## Claude's Discretion

- Library choices for Prometheus client
- OTel resource attributes beyond the specified fields
- Exact JSON log field ordering
- Middleware registration order

## Deferred Ideas

- LLM token count tracking as span attributes
- Custom Grafana dashboards
- Alerting rules for VictoriaMetrics
