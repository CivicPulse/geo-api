"""Tests for Phase 24 OSM CLI commands (PIPE-01..05).

Wave 0 scaffolded xfail stubs for every osm-* command; Plan 24-03 implements
TestOsmDownload and TestOsmDownloadRetry with real tests. Plans 04/05 will
remove remaining xfail markers as they implement their commands.
"""
from __future__ import annotations

import subprocess

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
# osm-import-nominatim (Plan 04 — IMPLEMENTED)
# ---------------------------------------------------------------------------


class TestOsmImportNominatim:
    def test_calls_docker_compose_exec_nominatim_import(self):
        with patch("civpulse_geo.cli.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            result = runner.invoke(app, ["osm-import-nominatim"])
        assert result.exit_code == 0, result.output
        mock_run.assert_called_once()
        called_args = mock_run.call_args[0][0]
        assert called_args[:5] == ["docker", "compose", "exec", "nominatim", "nominatim"]
        assert "import" in called_args
        assert "--osm-file" in called_args
        assert "/nominatim/pbf/georgia-latest.osm.pbf" in called_args
        assert "--threads" in called_args
        assert "4" in called_args


# ---------------------------------------------------------------------------
# osm-import-tiles (Plan 04 — IMPLEMENTED)
# ---------------------------------------------------------------------------


class TestOsmImportTiles:
    def test_calls_docker_compose_run_with_pbf_volume(self, tmp_path, monkeypatch):
        import civpulse_geo.cli as cli_module
        fake_pbf = tmp_path / "georgia-latest.osm.pbf"
        fake_pbf.write_bytes(b"fake")
        monkeypatch.setattr(cli_module, "PBF_PATH", fake_pbf)

        with patch("civpulse_geo.cli.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            result = runner.invoke(app, ["osm-import-tiles"])
        assert result.exit_code == 0, result.output
        mock_run.assert_called_once()
        called_args = mock_run.call_args[0][0]
        assert called_args[:5] == ["docker", "compose", "run", "--rm", "-v"]
        # Volume mount spec should end with :/data/region.osm.pbf:ro
        volume_spec = called_args[5]
        assert volume_spec.endswith(":/data/region.osm.pbf:ro")
        assert str(fake_pbf) in volume_spec
        assert called_args[-2:] == ["tile-server", "import"]


# ---------------------------------------------------------------------------
# osm-build-valhalla (Plan 04 — IMPLEMENTED)
# ---------------------------------------------------------------------------


class TestOsmBuildValhalla:
    def test_calls_docker_compose_run_with_force_rebuild(self):
        with patch("civpulse_geo.cli.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            result = runner.invoke(app, ["osm-build-valhalla"])
        assert result.exit_code == 0, result.output
        mock_run.assert_called_once()
        called_args = mock_run.call_args[0][0]
        assert called_args[:4] == ["docker", "compose", "run", "--rm"]
        assert called_args[-1] == "valhalla"
        # Must pass all four env flags per Pitfall 5
        assert "serve_tiles=False" in called_args
        assert "force_rebuild=True" in called_args
        assert "build_admins=False" in called_args
        assert "build_elevation=False" in called_args


# ---------------------------------------------------------------------------
# osm-pipeline (Plan 05 — Wave 0 stub)
# ---------------------------------------------------------------------------


class TestOsmPipeline:
    def test_runs_all_steps_in_order(self):
        # All idempotency checks return False -> all steps run
        # All run_fn (_invoke -> subprocess.run) succeed
        with patch("civpulse_geo.cli.subprocess.run") as mock_run:
            with patch("civpulse_geo.cli._check_pbf_exists", return_value=False), \
                 patch("civpulse_geo.cli._check_nominatim_populated", return_value=False), \
                 patch("civpulse_geo.cli._check_tiles_populated", return_value=False), \
                 patch("civpulse_geo.cli._check_valhalla_built", return_value=False):
                mock_run.return_value = MagicMock(returncode=0)
                result = runner.invoke(app, ["osm-pipeline"])
        assert result.exit_code == 0, result.output
        # Verify all 4 steps attempted (each _invoke calls subprocess.run once)
        assert mock_run.call_count == 4
        # Verify order by inspecting command names in calls
        commands_called = [call[0][0][3] for call in mock_run.call_args_list]
        assert commands_called == [
            "osm-download", "osm-import-nominatim", "osm-import-tiles", "osm-build-valhalla"
        ]

    def test_continues_after_step_failure(self):
        # Second step fails but third and fourth still run
        def side_effect(*args, **kwargs):
            cmd = args[0]
            # cmd is ["uv", "run", "geo-import", "osm-<name>"]
            if cmd[3] == "osm-import-nominatim":
                raise subprocess.CalledProcessError(1, cmd)
            return MagicMock(returncode=0)

        with patch("civpulse_geo.cli._check_pbf_exists", return_value=False), \
             patch("civpulse_geo.cli._check_nominatim_populated", return_value=False), \
             patch("civpulse_geo.cli._check_tiles_populated", return_value=False), \
             patch("civpulse_geo.cli._check_valhalla_built", return_value=False), \
             patch("civpulse_geo.cli.subprocess.run", side_effect=side_effect) as mock_run:
            result = runner.invoke(app, ["osm-pipeline"])
        # All 4 steps attempted even though step 2 failed
        assert mock_run.call_count == 4
        assert "FAIL" in result.output
        assert "osm-import-nominatim" in result.output
        assert "To retry:" in result.output

    def test_exits_nonzero_on_any_failure(self):
        def side_effect(*args, **kwargs):
            raise subprocess.CalledProcessError(1, args[0])

        with patch("civpulse_geo.cli._check_pbf_exists", return_value=False), \
             patch("civpulse_geo.cli._check_nominatim_populated", return_value=False), \
             patch("civpulse_geo.cli._check_tiles_populated", return_value=False), \
             patch("civpulse_geo.cli._check_valhalla_built", return_value=False), \
             patch("civpulse_geo.cli.subprocess.run", side_effect=side_effect):
            result = runner.invoke(app, ["osm-pipeline"])
        assert result.exit_code == 1

    def test_skips_completed_steps_when_idempotent(self):
        # All check functions return True -> all skip
        with patch("civpulse_geo.cli._check_pbf_exists", return_value=True), \
             patch("civpulse_geo.cli._check_nominatim_populated", return_value=True), \
             patch("civpulse_geo.cli._check_tiles_populated", return_value=True), \
             patch("civpulse_geo.cli._check_valhalla_built", return_value=True), \
             patch("civpulse_geo.cli.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = runner.invoke(app, ["osm-pipeline"])
        assert result.exit_code == 0, result.output
        assert mock_run.call_count == 0  # no steps actually ran
        assert result.output.count("SKIP") >= 4

    def test_force_reruns_all_steps(self):
        # Even when check functions return True, --force runs everything
        with patch("civpulse_geo.cli._check_pbf_exists", return_value=True), \
             patch("civpulse_geo.cli._check_nominatim_populated", return_value=True), \
             patch("civpulse_geo.cli._check_tiles_populated", return_value=True), \
             patch("civpulse_geo.cli._check_valhalla_built", return_value=True), \
             patch("civpulse_geo.cli.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = runner.invoke(app, ["osm-pipeline", "--force"])
        assert result.exit_code == 0, result.output
        assert mock_run.call_count == 4  # all 4 ran despite check=True
        assert "SKIP" not in result.output
