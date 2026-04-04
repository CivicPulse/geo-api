# Phase 23: E2E Testing, Load Baselines, and Final Validation - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-30
**Phase:** 23-e2e-testing-load-baselines-and-final-validation
**Areas discussed:** E2E test execution, Load test design, Observability verification, Final validation pass

---

## E2E Test Execution

### Connectivity

| Option | Description | Selected |
|--------|-------------|----------|
| kubectl port-forward | Tests run from dev machine, port-forward tunnels to pod. Simple, no cluster changes. | ✓ |
| In-cluster Job | Package tests as K8s Job running inside cluster via cluster DNS. | |
| Temporary NodePort | Patch Service to NodePort during testing, revert after. | |

**User's choice:** kubectl port-forward
**Notes:** Already mentioned in PROJECT.md as the access method for internal ClusterIP services.

### Test Location

| Option | Description | Selected |
|--------|-------------|----------|
| tests/e2e/ directory | Separate from unit tests, clear distinction, excludable via markers. | ✓ |
| e2e/ at project root | Top-level directory, fully separated from pytest suite. | |
| tests/ with pytest marks | Same directory, distinguished only by markers. | |

**User's choice:** tests/e2e/ directory
**Notes:** None

### Framework

| Option | Description | Selected |
|--------|-------------|----------|
| pytest + httpx | Same stack as existing unit tests but hitting real endpoints. | ✓ |
| pytest + requests | Synchronous HTTP client, simpler but can't reuse httpx fixtures. | |
| Standalone scripts | Plain Python scripts, maximum flexibility but no pytest features. | |

**User's choice:** pytest + httpx
**Notes:** None

### Test Data

| Option | Description | Selected |
|--------|-------------|----------|
| Macon-Bibb real addresses | Real addresses from the project's home jurisdiction. | ✓ |
| Fixture file with per-provider addresses | JSON/YAML fixture mapping each provider to known-good addresses. | ✓ |
| You decide | Claude picks appropriate test addresses. | |

**User's choice:** Both Macon-Bibb real addresses AND fixture file — a fixture file containing per-provider Macon-Bibb addresses.
**Notes:** User selected both options, combining structured fixture file approach with real Macon-Bibb addresses.

---

## Load Test Design

### Locust File Location

| Option | Description | Selected |
|--------|-------------|----------|
| loadtests/ at project root | Dedicated top-level directory, clean separation from pytest tests. | ✓ |
| tests/load/ | Under tests directory, keeps all testing together. | |
| You decide | Claude picks based on project conventions. | |

**User's choice:** loadtests/ at project root
**Notes:** None

### Cold-Cache vs Warm-Cache Separation

| Option | Description | Selected |
|--------|-------------|----------|
| Separate Locust runs | Two invocations, two reports: cold (unique addresses) then warm (repeated). | ✓ |
| Tagged within single run | Single run with two user classes, results split in post-processing. | |
| You decide | Claude picks what fits Locust's reporting model best. | |

**User's choice:** Separate Locust runs
**Notes:** None

### Endpoints Under Load

| Option | Description | Selected |
|--------|-------------|----------|
| Geocode + validate + cascade | Main request paths: /geocode, /validate, cascade pipeline. | ✓ |
| All endpoints including batch | Also /geocode/batch and /validate/batch with small batches. | |
| Geocode cascade only | Focus on most complex code path. | |

**User's choice:** Geocode + validate + cascade
**Notes:** Batch excluded to avoid skewing baselines.

### Duration and Ramp-Up

| Option | Description | Selected |
|--------|-------------|----------|
| 2-min ramp, 5-min sustain | 0→30 users over 2 min, sustain 5 min. ~7 min total per run. | ✓ |
| 1-min ramp, 10-min sustain | Faster ramp, longer sustain. ~22 min total with cold+warm. | |
| You decide | Claude picks based on statistical significance needs. | |

**User's choice:** 2-min ramp, 5-min sustain
**Notes:** None

---

## Observability Verification

### Verification Method

| Option | Description | Selected |
|--------|-------------|----------|
| Scripted CLI checks | Run queries against Loki/Tempo/VictoriaMetrics APIs post-load test. | ✓ |
| Manual Grafana spot-check | Visual confirmation via dashboards. | |
| Automated pytest assertions | E2E tests query observability backends programmatically. | |
| You decide | Claude picks approach balancing rigor and maintainability. | |

**User's choice:** Scripted CLI checks
**Notes:** None

### Script Format

| Option | Description | Selected |
|--------|-------------|----------|
| Shell scripts with curl | Bash + curl + jq, simple and portable. | |
| Python scripts with httpx | Python with httpx, more readable assertions. | ✓ |
| You decide | Claude picks simplest option for dev machine with kubectl. | |

**User's choice:** Python scripts with httpx
**Notes:** None

### Script Location

| Option | Description | Selected |
|--------|-------------|----------|
| scripts/verify/ | Under existing scripts/ directory alongside operational scripts. | ✓ |
| tests/e2e/ | Alongside E2E tests since they share deployment prerequisite. | |
| You decide | Claude picks best location. | |

**User's choice:** scripts/verify/
**Notes:** None

---

## Final Validation Pass

### Validation Format

| Option | Description | Selected |
|--------|-------------|----------|
| Markdown checklist | VALIDATION-CHECKLIST.md with 7 categories, pass/fail items, audit trail. | ✓ |
| Automated validation script | Python script checking each category programmatically. | |
| You decide | Claude picks balancing thoroughness with practical effort. | |

**User's choice:** Markdown checklist
**Notes:** None

### Blocker Handling

| Option | Description | Selected |
|--------|-------------|----------|
| Fix in-phase, re-run pass | Per VAL-01: fix blockers, re-run FULL pass until clean. Non-blockers logged per VAL-02. | ✓ |
| Fix blockers, spot-check only | Fix blockers, re-run only failed category. | |
| You decide | Claude determines re-run scope per fix severity. | |

**User's choice:** Fix in-phase, re-run full pass
**Notes:** None

### Checklist Location

| Option | Description | Selected |
|--------|-------------|----------|
| Phase directory | In .planning/phases/23-.../23-VALIDATION-CHECKLIST.md alongside phase artifacts. | ✓ |
| Project root | VALIDATION-CHECKLIST.md at root for visibility. | |
| You decide | Claude picks location fitting .planning structure. | |

**User's choice:** Phase directory
**Notes:** None

---

## Claude's Discretion

- Specific Macon-Bibb addresses for fixture file
- Locust task weighting between endpoints
- Loki/Tempo/VictoriaMetrics query syntax in verification scripts
- Validation checklist granularity within each category
- Helper script/Makefile for orchestrating port-forward + test runs

## Deferred Ideas

None — discussion stayed within phase scope
