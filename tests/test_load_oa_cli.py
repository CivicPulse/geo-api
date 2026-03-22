"""Tests for PIPE-05: load-oa CLI command registration and help text."""
import pytest
from typer.testing import CliRunner
from civpulse_geo.cli import app

runner = CliRunner()


class TestLoadOaCli:
    def test_load_oa_help_displays(self):
        """load-oa --help shows command description."""
        result = runner.invoke(app, ["load-oa", "--help"])
        assert result.exit_code == 0
        assert "openaddresses" in result.output.lower() or "geojson" in result.output.lower()

    def test_load_oa_registered_in_app(self):
        """load-oa appears in the CLI app's registered commands."""
        command_names = [cmd.name for cmd in app.registered_commands]
        assert "load-oa" in command_names

    def test_load_oa_missing_file_argument(self):
        """load-oa with no file argument exits with error."""
        result = runner.invoke(app, ["load-oa"])
        assert result.exit_code != 0

    def test_load_oa_nonexistent_file(self, tmp_path):
        """load-oa with nonexistent file exits with code 1."""
        result = runner.invoke(app, ["load-oa", str(tmp_path / "missing.geojson.gz")])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()
