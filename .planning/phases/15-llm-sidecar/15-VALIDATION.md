---
phase: 15
slug: llm-sidecar
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-29
---

# Phase 15 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `python -m pytest tests/ -x -q --timeout=30` |
| **Full suite command** | `python -m pytest tests/ -v --timeout=60` |
| **Estimated runtime** | ~45 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/ -x -q --timeout=30`
- **After every plan wave:** Run `python -m pytest tests/ -v --timeout=60`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 45 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 15-01-01 | 01 | 1 | LLM-01 | integration | `python -m pytest tests/test_llm_corrector.py -k ollama_service` | ❌ W0 | ⬜ pending |
| 15-01-02 | 01 | 1 | LLM-01 | integration | `python -m pytest tests/test_llm_corrector.py -k model_available` | ❌ W0 | ⬜ pending |
| 15-02-01 | 02 | 2 | LLM-02 | unit | `python -m pytest tests/test_llm_corrector.py -k structured_json` | ❌ W0 | ⬜ pending |
| 15-02-02 | 02 | 2 | LLM-02 | integration | `python -m pytest tests/test_llm_corrector.py -k reverify` | ❌ W0 | ⬜ pending |
| 15-03-01 | 02 | 2 | LLM-03 | unit | `python -m pytest tests/test_llm_corrector.py -k state_mismatch_reject` | ❌ W0 | ⬜ pending |
| 15-03-02 | 02 | 2 | LLM-03 | unit | `python -m pytest tests/test_llm_corrector.py -k zip_state_guard` | ❌ W0 | ⬜ pending |
| 15-04-01 | 02 | 2 | LLM-04 | integration | `python -m pytest tests/test_llm_corrector.py -k graceful_degradation` | ❌ W0 | ⬜ pending |
| 15-04-02 | 02 | 2 | LLM-04 | integration | `python -m pytest tests/test_llm_corrector.py -k ollama_unavailable` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_llm_corrector.py` — stubs for LLM-01, LLM-02, LLM-03, LLM-04
- [ ] Test fixtures for mocking Ollama HTTP responses (structured JSON, timeout, unavailable)

*Existing pytest infrastructure and httpx mock patterns cover framework needs.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Docker Compose model pull on first start | LLM-01 | Requires fresh Docker volume | Start with empty volume, verify qwen2.5:3b pulled automatically |

*All other behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 45s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
