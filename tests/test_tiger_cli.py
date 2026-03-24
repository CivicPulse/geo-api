"""Tests for setup-tiger CLI command — FIPS conversion and extension installation.

Tests verify:
- FIPS_TO_ABBREV dict has correct spot-check entries and 51 total entries
- _resolve_state converts FIPS codes, passes through abbreviations case-insensitively
- _resolve_state returns None for unknown codes
- setup-tiger CLI exits 1 for unknown FIPS codes
- setup-tiger CLI calls CREATE EXTENSION for all 4 Tiger extensions
- setup-tiger CLI calls Loader_Generate_Script with state abbreviation (not FIPS code)
- setup-tiger CLI handles multiple states
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch, call
from typer.testing import CliRunner

from civpulse_geo.cli import app
from civpulse_geo.cli import _resolve_state, FIPS_TO_ABBREV

runner = CliRunner()


# ---------------------------------------------------------------------------
# FIPS conversion tests
# ---------------------------------------------------------------------------

class TestFipsConversion:
    """Tests for FIPS_TO_ABBREV dict and _resolve_state helper."""

    def test_fips_to_abbrev_spot_check_ga(self):
        """FIPS 13 maps to GA."""
        assert FIPS_TO_ABBREV["13"] == "GA"

    def test_fips_to_abbrev_spot_check_al(self):
        """FIPS 01 maps to AL."""
        assert FIPS_TO_ABBREV["01"] == "AL"

    def test_fips_to_abbrev_spot_check_ca(self):
        """FIPS 06 maps to CA."""
        assert FIPS_TO_ABBREV["06"] == "CA"

    def test_fips_to_abbrev_has_51_entries(self):
        """Dict has exactly 51 entries (50 states + DC)."""
        assert len(FIPS_TO_ABBREV) == 51

    def test_resolve_state_fips_code(self):
        """FIPS code '13' resolves to 'GA'."""
        assert _resolve_state("13") == "GA"

    def test_resolve_state_abbreviation_passthrough(self):
        """State abbreviation 'GA' resolves to 'GA'."""
        assert _resolve_state("GA") == "GA"

    def test_resolve_state_abbreviation_case_insensitive(self):
        """Lowercase abbreviation 'ga' resolves to 'GA'."""
        assert _resolve_state("ga") == "GA"

    def test_resolve_state_mixed_case_abbreviation(self):
        """Mixed case abbreviation 'Ga' resolves to 'GA'."""
        assert _resolve_state("Ga") == "GA"

    def test_resolve_state_unknown_fips(self):
        """Unknown FIPS code '99' returns None."""
        assert _resolve_state("99") is None

    def test_resolve_state_unknown_abbreviation(self):
        """Unknown abbreviation 'ZZ' returns None."""
        assert _resolve_state("ZZ") is None

    def test_resolve_state_fips_with_leading_whitespace(self):
        """FIPS code with whitespace is handled."""
        assert _resolve_state(" 13 ") == "GA"

    def test_resolve_state_al(self):
        """FIPS code '01' resolves to 'AL'."""
        assert _resolve_state("01") == "AL"

    def test_resolve_state_dc(self):
        """FIPS code '11' resolves to 'DC'."""
        assert _resolve_state("11") == "DC"


# ---------------------------------------------------------------------------
# setup-tiger CLI tests
# ---------------------------------------------------------------------------

def _make_mock_engine():
    """Build a mock engine with connect() context manager support."""
    mock_conn = MagicMock()
    mock_engine = MagicMock()
    mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
    mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)
    # Default: Loader_Generate_Script returns a trivial script
    mock_conn.execute.return_value.scalar.return_value = "#!/bin/bash\necho loaded"
    return mock_engine, mock_conn


class TestSetupTigerCLI:
    """Tests for setup-tiger Typer CLI command."""

    @patch("civpulse_geo.cli.create_engine")
    def test_unknown_fips_exits_1(self, mock_create_engine):
        """Unknown FIPS code '99' causes exit code 1."""
        result = runner.invoke(app, ["setup-tiger", "99"])
        assert result.exit_code == 1

    @patch("civpulse_geo.cli.create_engine")
    def test_unknown_fips_prints_error(self, mock_create_engine):
        """Unknown FIPS code '99' prints an error message."""
        result = runner.invoke(app, ["setup-tiger", "99"])
        assert "99" in result.output or "99" in (result.stderr or "")

    @patch("subprocess.run")
    @patch("civpulse_geo.cli.create_engine")
    def test_valid_fips_calls_create_engine(self, mock_create_engine, mock_subprocess):
        """Valid FIPS '13' results in create_engine being called."""
        mock_engine, mock_conn = _make_mock_engine()
        mock_create_engine.return_value = mock_engine
        mock_subprocess.return_value = MagicMock(returncode=0, stdout="", stderr="")

        result = runner.invoke(app, ["setup-tiger", "13"])
        assert result.exit_code == 0
        mock_create_engine.assert_called_once()

    @patch("subprocess.run")
    @patch("civpulse_geo.cli.create_engine")
    def test_installs_exactly_4_extensions(self, mock_create_engine, mock_subprocess):
        """setup-tiger installs exactly 4 Tiger extensions."""
        mock_engine, mock_conn = _make_mock_engine()
        mock_create_engine.return_value = mock_engine
        mock_subprocess.return_value = MagicMock(returncode=0, stdout="", stderr="")

        result = runner.invoke(app, ["setup-tiger", "13"])
        assert result.exit_code == 0

        # Count CREATE EXTENSION calls — text() args are TextClause objects;
        # convert each arg to string using its .text attribute or str()
        def _sql_text(call_obj) -> str:
            args = call_obj[0]
            if args:
                arg = args[0]
                return getattr(arg, "text", str(arg))
            return ""

        create_ext_calls = [
            c for c in mock_conn.execute.call_args_list
            if "CREATE EXTENSION" in _sql_text(c)
        ]
        assert len(create_ext_calls) == 4

    @patch("subprocess.run")
    @patch("civpulse_geo.cli.create_engine")
    def test_installs_fuzzystrmatch(self, mock_create_engine, mock_subprocess):
        """fuzzystrmatch extension is installed."""
        mock_engine, mock_conn = _make_mock_engine()
        mock_create_engine.return_value = mock_engine
        mock_subprocess.return_value = MagicMock(returncode=0, stdout="", stderr="")

        runner.invoke(app, ["setup-tiger", "13"])

        all_sql = " ".join(
            getattr(c[0][0], "text", str(c[0][0])) if c[0] else ""
            for c in mock_conn.execute.call_args_list
        )
        assert "fuzzystrmatch" in all_sql

    @patch("subprocess.run")
    @patch("civpulse_geo.cli.create_engine")
    def test_installs_postgis_tiger_geocoder(self, mock_create_engine, mock_subprocess):
        """postgis_tiger_geocoder extension is installed."""
        mock_engine, mock_conn = _make_mock_engine()
        mock_create_engine.return_value = mock_engine
        mock_subprocess.return_value = MagicMock(returncode=0, stdout="", stderr="")

        runner.invoke(app, ["setup-tiger", "13"])

        all_sql = " ".join(
            getattr(c[0][0], "text", str(c[0][0])) if c[0] else ""
            for c in mock_conn.execute.call_args_list
        )
        assert "postgis_tiger_geocoder" in all_sql

    @patch("subprocess.run")
    @patch("civpulse_geo.cli.create_engine")
    def test_calls_loader_generate_script_with_abbreviation(self, mock_create_engine, mock_subprocess):
        """Loader_Generate_Script is called with 'GA' abbreviation, not '13' FIPS code."""
        mock_engine, mock_conn = _make_mock_engine()
        mock_create_engine.return_value = mock_engine
        mock_subprocess.return_value = MagicMock(returncode=0, stdout="", stderr="")

        result = runner.invoke(app, ["setup-tiger", "13"])
        assert result.exit_code == 0

        # Verify Loader_Generate_Script appears in SQL
        all_sql = " ".join(
            getattr(c[0][0], "text", str(c[0][0])) if c[0] else ""
            for c in mock_conn.execute.call_args_list
        )
        assert "Loader_Generate_Script" in all_sql

        # Verify the parameter passed was the abbreviation GA (not FIPS 13)
        all_params = " ".join(str(c) for c in mock_conn.execute.call_args_list)
        assert "GA" in all_params

    @patch("subprocess.run")
    @patch("civpulse_geo.cli.create_engine")
    def test_multiple_states_processes_both(self, mock_create_engine, mock_subprocess):
        """Multiple states '13 01' processes both GA and AL."""
        mock_engine, mock_conn = _make_mock_engine()
        mock_create_engine.return_value = mock_engine
        mock_subprocess.return_value = MagicMock(returncode=0, stdout="", stderr="")

        result = runner.invoke(app, ["setup-tiger", "13", "01"])
        assert result.exit_code == 0

        all_params = " ".join(str(c) for c in mock_conn.execute.call_args_list)
        # Both GA and AL should appear in the calls
        assert "GA" in all_params
        assert "AL" in all_params

    @patch("subprocess.run")
    @patch("civpulse_geo.cli.create_engine")
    def test_abbreviation_input_accepted(self, mock_create_engine, mock_subprocess):
        """State abbreviation 'GA' is accepted directly."""
        mock_engine, mock_conn = _make_mock_engine()
        mock_create_engine.return_value = mock_engine
        mock_subprocess.return_value = MagicMock(returncode=0, stdout="", stderr="")

        result = runner.invoke(app, ["setup-tiger", "GA"])
        assert result.exit_code == 0

    @patch("subprocess.run")
    @patch("civpulse_geo.cli.create_engine")
    def test_lowercase_abbreviation_accepted(self, mock_create_engine, mock_subprocess):
        """Lowercase state abbreviation 'ga' is accepted."""
        mock_engine, mock_conn = _make_mock_engine()
        mock_create_engine.return_value = mock_engine
        mock_subprocess.return_value = MagicMock(returncode=0, stdout="", stderr="")

        result = runner.invoke(app, ["setup-tiger", "ga"])
        assert result.exit_code == 0
