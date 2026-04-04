"""Tests for Phase 24 OSM CLI commands (PIPE-01..05).

Wave 0 scaffolded xfail stubs for every osm-* command; Plan 24-03 implements
TestOsmDownload and TestOsmDownloadRetry with real tests. Plans 04/05 will
remove remaining xfail markers as they implement their commands.
"""
from __future__ import annotations

import pytest
import httpx
from typer.testing import CliRunner
from unittest.mock import patch, MagicMock

from civpulse_geo.cli import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# osm-download (Plan 03 — IMPLEMENTED)
# ---------------------------------------------------------------------------


class TestOsmDownload:
    def test_download_creates_pbf_file(self, tmp_path, monkeypatch):
        import civpulse_geo.cli as cli_module
        fake_pbf = tmp_path / "georgia-latest.osm.pbf"
        monkeypatch.setattr(cli_module, "OSM_DATA_DIR", tmp_path)
        monkeypatch.setattr(cli_module, "PBF_PATH", fake_pbf)

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.iter_bytes = MagicMock(return_value=[b"fake pbf content"])
        mock_cm = MagicMock()
        mock_cm.__enter__ = MagicMock(return_value=mock_response)
        mock_cm.__exit__ = MagicMock(return_value=False)

        with patch("civpulse_geo.cli.httpx.stream", return_value=mock_cm) as mock_stream:
            result = runner.invoke(app, ["osm-download"])

        assert result.exit_code == 0, result.output
        mock_stream.assert_called_once()
        assert fake_pbf.exists()
        assert fake_pbf.read_bytes() == b"fake pbf content"

    def test_download_skips_when_file_exists(self, tmp_path, monkeypatch):
        import civpulse_geo.cli as cli_module
        fake_pbf = tmp_path / "georgia-latest.osm.pbf"
        fake_pbf.write_bytes(b"existing")
        monkeypatch.setattr(cli_module, "OSM_DATA_DIR", tmp_path)
        monkeypatch.setattr(cli_module, "PBF_PATH", fake_pbf)

        with patch("civpulse_geo.cli.httpx.stream") as mock_stream:
            result = runner.invoke(app, ["osm-download"])

        assert result.exit_code == 0
        assert "already exists" in result.output
        mock_stream.assert_not_called()
        assert fake_pbf.read_bytes() == b"existing"

    def test_download_force_redownloads(self, tmp_path, monkeypatch):
        import civpulse_geo.cli as cli_module
        fake_pbf = tmp_path / "georgia-latest.osm.pbf"
        fake_pbf.write_bytes(b"old")
        monkeypatch.setattr(cli_module, "OSM_DATA_DIR", tmp_path)
        monkeypatch.setattr(cli_module, "PBF_PATH", fake_pbf)

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.iter_bytes = MagicMock(return_value=[b"new content"])
        mock_cm = MagicMock()
        mock_cm.__enter__ = MagicMock(return_value=mock_response)
        mock_cm.__exit__ = MagicMock(return_value=False)

        with patch("civpulse_geo.cli.httpx.stream", return_value=mock_cm) as mock_stream:
            result = runner.invoke(app, ["osm-download", "--force"])

        assert result.exit_code == 0
        mock_stream.assert_called_once()
        assert fake_pbf.read_bytes() == b"new content"


class TestOsmDownloadRetry:
    def test_download_retries_3x_on_network_failure(self, tmp_path, monkeypatch):
        import civpulse_geo.cli as cli_module
        fake_pbf = tmp_path / "georgia-latest.osm.pbf"
        monkeypatch.setattr(cli_module, "OSM_DATA_DIR", tmp_path)
        monkeypatch.setattr(cli_module, "PBF_PATH", fake_pbf)

        # First two attempts raise, third succeeds
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.iter_bytes = MagicMock(return_value=[b"ok"])
        success_cm = MagicMock()
        success_cm.__enter__ = MagicMock(return_value=mock_response)
        success_cm.__exit__ = MagicMock(return_value=False)

        call_count = {"n": 0}

        def side_effect(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] < 3:
                raise httpx.ConnectError("network down")
            return success_cm

        with patch("civpulse_geo.cli.httpx.stream", side_effect=side_effect) as mock_stream:
            with patch("civpulse_geo.cli.time.sleep") as mock_sleep:
                result = runner.invoke(app, ["osm-download"])

        assert result.exit_code == 0, result.output
        assert mock_stream.call_count == 3
        assert mock_sleep.call_args_list == [((1,),), ((2,),)]


# ---------------------------------------------------------------------------
# osm-import-nominatim (Plan 04 — Wave 0 stub)
# ---------------------------------------------------------------------------


class TestOsmImportNominatim:
    @pytest.mark.xfail(reason="Wave 0 stub — implemented in Plan 04", strict=False)
    def test_calls_docker_compose_exec_nominatim_import(self):
        pass  # Plan 04 implements


# ---------------------------------------------------------------------------
# osm-import-tiles (Plan 04 — Wave 0 stub)
# ---------------------------------------------------------------------------


class TestOsmImportTiles:
    @pytest.mark.xfail(reason="Wave 0 stub — implemented in Plan 04", strict=False)
    def test_calls_docker_compose_run_with_pbf_volume(self):
        pass  # Plan 04 implements


# ---------------------------------------------------------------------------
# osm-build-valhalla (Plan 04 — Wave 0 stub)
# ---------------------------------------------------------------------------


class TestOsmBuildValhalla:
    @pytest.mark.xfail(reason="Wave 0 stub — implemented in Plan 04", strict=False)
    def test_calls_docker_compose_run_with_force_rebuild(self):
        pass  # Plan 04 implements


# ---------------------------------------------------------------------------
# osm-pipeline (Plan 05 — Wave 0 stub)
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
