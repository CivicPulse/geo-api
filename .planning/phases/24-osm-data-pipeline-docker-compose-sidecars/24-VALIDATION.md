---
phase: 24
slug: osm-data-pipeline-docker-compose-sidecars
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-04
---

# Phase 24 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x |
| **Config file** | pyproject.toml (tool.pytest.ini_options) |
| **Quick run command** | `uv run pytest tests/ -x --ff -q` |
| **Full suite command** | `uv run pytest tests/ -v` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -x --ff -q`
- **After every plan wave:** Run `uv run pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 24-01-01 | 01 | 1 | PIPE-01 | unit | `uv run pytest tests/osm/test_pbf_download.py -v` | ❌ W0 | ⬜ pending |
| 24-01-02 | 01 | 1 | PIPE-01 | integration | `uv run pytest tests/osm/test_pbf_download.py::test_download_cli -v` | ❌ W0 | ⬜ pending |
| 24-02-01 | 02 | 2 | INFRA-01,INFRA-02,INFRA-03 | integration | `docker compose config -q && docker compose up -d osm-postgres nominatim tile-server valhalla` | ❌ W0 | ⬜ pending |
| 24-03-01 | 03 | 3 | PIPE-02 | unit | `uv run pytest tests/osm/test_nominatim_import.py -v` | ❌ W0 | ⬜ pending |
| 24-04-01 | 04 | 3 | PIPE-03 | unit | `uv run pytest tests/osm/test_tile_import.py -v` | ❌ W0 | ⬜ pending |
| 24-05-01 | 05 | 3 | PIPE-04 | unit | `uv run pytest tests/osm/test_valhalla_build.py -v` | ❌ W0 | ⬜ pending |
| 24-06-01 | 06 | 4 | PIPE-05 | integration | `uv run pytest tests/osm/test_pipeline_cli.py -v` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/osm/__init__.py` — package marker
- [ ] `tests/osm/conftest.py` — shared fixtures (temp directories, mocked docker commands)
- [ ] `tests/osm/test_pbf_download.py` — stubs for PIPE-01
- [ ] `tests/osm/test_nominatim_import.py` — stubs for PIPE-02
- [ ] `tests/osm/test_tile_import.py` — stubs for PIPE-03
- [ ] `tests/osm/test_valhalla_build.py` — stubs for PIPE-04
- [ ] `tests/osm/test_pipeline_cli.py` — stubs for PIPE-05

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| `docker compose up` starts all sidecars | INFRA-01 | Requires Docker daemon + network egress for image pulls (first run) | Run `docker compose up -d osm-postgres nominatim tile-server valhalla`, then `docker compose ps` — verify all 4 services report healthy within 120 seconds |
| End-to-end pipeline on clean env | PIPE-05 | Requires ~3GB PBF download + ~30min Nominatim import on real hardware | Run `uv run civpulse-geo osm pipeline --region georgia` on a clean volume; verify all 3 sidecars populated |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
