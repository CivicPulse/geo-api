"""Wave 0 stub tests for osm-* CLI commands.

Every test is marked xfail — they fail predictably until the corresponding
Plan (03, 04, 05) implements each command.  These stubs establish the test
harness that downstream plans drive implementation against (Nyquist compliance).
"""
from __future__ import annotations

import pytest
from typer.testing import CliRunner
from unittest.mock import patch, MagicMock  # noqa: F401 — used in Plan 03/04/05 implementations

from civpulse_geo.cli import app  # noqa: F401 — used by runner.invoke stubs below

runner = CliRunner()


# ---------------------------------------------------------------------------
# osm-download (Plan 03)
# ---------------------------------------------------------------------------


class TestOsmDownload:
    @pytest.mark.xfail(reason="Wave 0 stub — implemented in Plan 03", strict=False)
    def test_download_creates_pbf_file(self, tmp_path):
        pass  # Plan 03 implements

    @pytest.mark.xfail(reason="Wave 0 stub — implemented in Plan 03", strict=False)
    def test_download_skips_when_file_exists(self, tmp_path):
        pass  # Plan 03 implements

    @pytest.mark.xfail(reason="Wave 0 stub — implemented in Plan 03", strict=False)
    def test_download_force_redownloads(self, tmp_path):
        pass  # Plan 03 implements


class TestOsmDownloadRetry:
    @pytest.mark.xfail(reason="Wave 0 stub — implemented in Plan 03", strict=False)
    def test_download_retries_3x_on_network_failure(self):
        pass  # Plan 03 implements


# ---------------------------------------------------------------------------
# osm-import-nominatim (Plan 04)
# ---------------------------------------------------------------------------


class TestOsmImportNominatim:
    @pytest.mark.xfail(reason="Wave 0 stub — implemented in Plan 04", strict=False)
    def test_calls_docker_compose_exec_nominatim_import(self):
        pass  # Plan 04 implements


# ---------------------------------------------------------------------------
# osm-import-tiles (Plan 04)
# ---------------------------------------------------------------------------


class TestOsmImportTiles:
    @pytest.mark.xfail(reason="Wave 0 stub — implemented in Plan 04", strict=False)
    def test_calls_docker_compose_run_with_pbf_volume(self):
        pass  # Plan 04 implements


# ---------------------------------------------------------------------------
# osm-build-valhalla (Plan 04)
# ---------------------------------------------------------------------------


class TestOsmBuildValhalla:
    @pytest.mark.xfail(reason="Wave 0 stub — implemented in Plan 04", strict=False)
    def test_calls_docker_compose_run_with_force_rebuild(self):
        pass  # Plan 04 implements


# ---------------------------------------------------------------------------
# osm-pipeline (Plan 05)
# ---------------------------------------------------------------------------


class TestOsmPipeline:
    @pytest.mark.xfail(reason="Wave 0 stub — implemented in Plan 05", strict=False)
    def test_runs_all_steps_in_order(self):
        pass  # Plan 05 implements

    @pytest.mark.xfail(reason="Wave 0 stub — implemented in Plan 05", strict=False)
    def test_continues_after_step_failure(self):
        pass  # Plan 05 implements

    @pytest.mark.xfail(reason="Wave 0 stub — implemented in Plan 05", strict=False)
    def test_exits_nonzero_on_any_failure(self):
        pass  # Plan 05 implements

    @pytest.mark.xfail(reason="Wave 0 stub — implemented in Plan 05", strict=False)
    def test_skips_completed_steps_when_idempotent(self):
        pass  # Plan 05 implements

    @pytest.mark.xfail(reason="Wave 0 stub — implemented in Plan 05", strict=False)
    def test_force_reruns_all_steps(self):
        pass  # Plan 05 implements
