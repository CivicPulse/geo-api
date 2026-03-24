"""Tests for load-nad CLI command registration, help text, and full COPY import."""
import csv
import io
import zipfile
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from civpulse_geo.cli import app

runner = CliRunner()


class TestLoadNadCli:
    def test_load_nad_help_displays(self):
        """load-nad --help shows command description."""
        result = runner.invoke(app, ["load-nad", "--help"])
        assert result.exit_code == 0
        assert "nad" in result.output.lower() or "zip" in result.output.lower()

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
        result = runner.invoke(app, ["load-nad", str(tmp_path / "missing.zip"), "--state", "GA"])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()

    def test_load_nad_requires_state(self, tmp_path):
        """load-nad without --state flag exits with non-zero code and shows state error."""
        # Create a minimal valid ZIP with a TXT CSV inside
        zip_path = tmp_path / "NAD_r21_TXT.zip"
        _make_test_zip(zip_path, rows=[_make_csv_row()])
        result = runner.invoke(app, ["load-nad", str(zip_path)])
        assert result.exit_code != 0

    def test_load_nad_invalid_state(self, tmp_path):
        """load-nad with an invalid --state argument exits with error about unknown state."""
        zip_path = tmp_path / "NAD_r21_TXT.zip"
        _make_test_zip(zip_path, rows=[_make_csv_row()])
        result = runner.invoke(app, ["load-nad", str(zip_path), "--state", "XX"])
        assert result.exit_code != 0
        assert "unknown state" in result.output.lower()


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------

NAD_FIELDNAMES = [
    "OID_", "UUID", "Add_Number", "AddNo_Full", "St_Name", "St_PosTyp", "St_PosDir",
    "St_PosMod", "Unit", "City", "County", "State", "Zip_Code", "Plus_4", "UUID2",
    "AddrRange", "LandmkName", "LandmkType", "PlaceNm", "Longitude", "Latitude",
    "NatGrid", "Placement", "AddrPoint", "DateUpdate", "Effective", "Expire",
    "Inc_Muni", "Uninc_Comm", "Nbrhd_Comm", "AddAuth", "AddrRefSys", "Post_City",
    "Post_Code", "Post_Code4", "Post_Comm", "Parcel_ID", "SubAddress", "Building",
    "Floor", "Room", "Seat", "AddtlLoc", "Add_Range", "Parity", "LandmkPart",
    "RCL_Side", "USNG", "ESN", "PSAP_ID", "MSAGComm", "Source", "DateAdded",
    "DataSet", "MilePost", "StrucPart", "StrucGrp", "County_FIPS", "State_FIPS",
    "CensusTract", "CensusBlock",
]


def _make_csv_row(**overrides):
    """Return a dict with all NAD CSV columns, sane defaults, with optional overrides."""
    base = {
        "UUID": "{0EDDC2DD-6521-4EC7-B87B-AE4697521050}",
        "Add_Number": "123",
        "St_Name": "MAIN",
        "St_PosTyp": "ST",
        "Unit": "",
        "Post_City": "MACON",
        "Inc_Muni": "",
        "County": "Bibb",
        "State": "GA",
        "Zip_Code": "31201",
        "Longitude": "-83.63",
        "Latitude": "32.84",
        "Placement": "Unknown",
    }
    # Fill remaining required fieldnames with empty strings
    for field in NAD_FIELDNAMES:
        if field not in base:
            base[field] = ""
    base.update(overrides)
    return base


def _make_test_zip(zip_path, rows):
    """Create a minimal ZIP file with a CSV TXT file inside."""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=NAD_FIELDNAMES)
    writer.writeheader()
    writer.writerows(rows)

    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("NAD_r21_TXT.txt", buf.getvalue())


# ---------------------------------------------------------------------------
# _resolve_city tests
# ---------------------------------------------------------------------------

class TestResolveCityFallback:
    """Tests for the _resolve_city helper."""

    def test_post_city_not_stated_uses_inc_muni(self):
        """Post_City 'Not stated' is skipped; Inc_Muni is returned."""
        from civpulse_geo.cli import _resolve_city
        assert _resolve_city("Not stated", "City of Sand Point", "Borough") == "City of Sand Point"

    def test_post_city_first_when_available(self):
        """Post_City is returned when non-empty and not 'Not stated'."""
        from civpulse_geo.cli import _resolve_city
        assert _resolve_city("Anchorage", "City of Anchorage", "Anchorage") == "Anchorage"

    def test_all_empty_returns_none(self):
        """All empty strings returns None."""
        from civpulse_geo.cli import _resolve_city
        assert _resolve_city("", "", "") is None

    def test_all_not_stated_returns_none(self):
        """All 'Not stated' values returns None."""
        from civpulse_geo.cli import _resolve_city
        assert _resolve_city("Not stated", "Not stated", "Not stated") is None

    def test_case_insensitive_not_stated(self):
        """'Not Stated' (mixed case) is treated as not-stated, falls through to county."""
        from civpulse_geo.cli import _resolve_city
        assert _resolve_city("Not Stated", "", "Bibb County") == "Bibb County"


# ---------------------------------------------------------------------------
# _parse_nad_row tests
# ---------------------------------------------------------------------------

class TestParseNadRow:
    """Tests for the _parse_nad_row helper."""

    def test_strips_uuid_braces(self):
        """UUID with braces is stripped to plain 36-char UUID string."""
        from civpulse_geo.cli import _parse_nad_row
        row = _make_csv_row()
        stats = {"skipped": 0}
        result = _parse_nad_row(row, stats)
        assert result is not None
        assert result[0] == "0EDDC2DD-6521-4EC7-B87B-AE4697521050"

    def test_builds_wkt_point(self):
        """Longitude and Latitude become a WKT POINT in SRID=4326 format."""
        from civpulse_geo.cli import _parse_nad_row
        row = _make_csv_row(Longitude="-149.43", Latitude="61.22")
        stats = {"skipped": 0}
        result = _parse_nad_row(row, stats)
        assert result is not None
        assert result[8] == "SRID=4326;POINT(-149.43 61.22)"

    def test_column_mapping(self):
        """Core columns map correctly: number, name, suffix, unit, state, zip, placement."""
        from civpulse_geo.cli import _parse_nad_row
        row = _make_csv_row(
            Add_Number="456",
            St_Name="OAK",
            St_PosTyp="AVE",
            Unit="APT 2",
            State="FL",
            Zip_Code="32801",
            Placement="Parcel",
        )
        stats = {"skipped": 0}
        result = _parse_nad_row(row, stats)
        assert result is not None
        assert result[1] == "456"      # street_number
        assert result[2] == "OAK"      # street_name
        assert result[3] == "AVE"      # street_suffix
        assert result[4] == "APT 2"    # unit
        assert result[6] == "FL"       # state
        assert result[7] == "32801"    # zip_code
        assert result[9] == "Parcel"   # placement

    def test_skips_missing_longitude(self):
        """Row with empty Longitude returns None and increments stats['skipped']."""
        from civpulse_geo.cli import _parse_nad_row
        row = _make_csv_row(Longitude="")
        stats = {"skipped": 0}
        result = _parse_nad_row(row, stats)
        assert result is None
        assert stats["skipped"] == 1

    def test_skips_missing_latitude(self):
        """Row with empty Latitude returns None and increments stats['skipped']."""
        from civpulse_geo.cli import _parse_nad_row
        row = _make_csv_row(Latitude="")
        stats = {"skipped": 0}
        result = _parse_nad_row(row, stats)
        assert result is None
        assert stats["skipped"] == 1

    def test_city_fallback_applied(self):
        """City fallback: Post_City used when not 'Not stated'."""
        from civpulse_geo.cli import _parse_nad_row
        row = _make_csv_row(Post_City="MACON", Inc_Muni="", County="Bibb")
        stats = {"skipped": 0}
        result = _parse_nad_row(row, stats)
        assert result is not None
        assert result[5] == "MACON"    # city
