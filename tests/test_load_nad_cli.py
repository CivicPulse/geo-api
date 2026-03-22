"""Tests for PIPE-06: load-nad CLI command registration and help text."""
import pytest
from typer.testing import CliRunner
from civpulse_geo.cli import app

runner = CliRunner()


class TestLoadNadCli:
    def test_load_nad_help_displays(self):
        """load-nad --help shows command description."""
        result = runner.invoke(app, ["load-nad", "--help"])
        assert result.exit_code == 0
        assert "nad" in result.output.lower() or "txt" in result.output.lower()

    def test_load_nad_registered_in_app(self):
        """load-nad appears in the CLI app's registered commands."""
        command_names = [cmd.name for cmd in app.registered_commands]
        assert "load-nad" in command_names

    def test_load_nad_missing_file_argument(self):
        """load-nad with no file argument exits with error."""
        result = runner.invoke(app, ["load-nad"])
        assert result.exit_code != 0

    def test_load_nad_nonexistent_file(self, tmp_path):
        """load-nad with nonexistent file exits with code 1."""
        result = runner.invoke(app, ["load-nad", str(tmp_path / "missing.txt")])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()
