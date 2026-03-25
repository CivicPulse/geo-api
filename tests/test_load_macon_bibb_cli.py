"""Tests for load-macon-bibb CLI command registration, extension validation, and import."""
import json
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from civpulse_geo.cli import app

runner = CliRunner()


class TestLoadMaconBibbCli:
    def test_load_macon_bibb_registered_in_app(self):
        """load-macon-bibb appears in the CLI app's registered commands."""
        command_names = [cmd.name for cmd in app.registered_commands]
        assert "load-macon-bibb" in command_names

    def test_load_macon_bibb_help_displays(self):
        """load-macon-bibb --help shows command description."""
        result = runner.invoke(app, ["load-macon-bibb", "--help"])
        assert result.exit_code == 0
        assert "macon" in result.output.lower() or "bibb" in result.output.lower()

    def test_load_macon_bibb_missing_file_argument(self):
        """load-macon-bibb with no file argument exits with error."""
        result = runner.invoke(app, ["load-macon-bibb"])
        assert result.exit_code != 0

    def test_load_macon_bibb_nonexistent_file(self, tmp_path):
        """load-macon-bibb with nonexistent .geojson file exits with code 1."""
        result = runner.invoke(app, ["load-macon-bibb", str(tmp_path / "missing.geojson")])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()

    def test_load_macon_bibb_rejects_non_geojson_extension(self, tmp_path):
        """load-macon-bibb with a .txt file exits with code 1 about wrong extension."""
        bad_file = tmp_path / "data.txt"
        bad_file.write_text("not geojson")
        result = runner.invoke(app, ["load-macon-bibb", str(bad_file)])
        assert result.exit_code == 1
        assert "geojson" in result.output.lower()

    def test_load_macon_bibb_rejects_geojson_gz_extension(self, tmp_path):
        """load-macon-bibb rejects .geojson.gz (must be uncompressed .geojson)."""
        bad_file = tmp_path / "data.geojson.gz"
        bad_file.write_bytes(b"fake gz content")
        result = runner.invoke(app, ["load-macon-bibb", str(bad_file)])
        assert result.exit_code == 1

    def test_load_macon_bibb_accepts_valid_geojson(self, tmp_path):
        """load-macon-bibb with a valid .geojson file runs successfully (mocked DB)."""
        geojson_data = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {
                        "OBJECTID": 1,
                        "ADDR_HN": "489",
                        "ADDR_SN": "NORTHMINSTER",
                        "ADDR_ST": "DR",
                        "UNIT": " ",
                        "City_1": "MACON",
                        "ZIP_1": "31204",
                        "ADDType": "PARCEL",
                        "FULLADDR": "489 NORTHMINSTER DR",
                    },
                    "geometry": {
                        "type": "Point",
                        "coordinates": [-83.687, 32.872],
                    },
                }
            ],
        }
        geojson_file = tmp_path / "Address_Points.geojson"
        geojson_file.write_text(json.dumps(geojson_data))

        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = True  # was_inserted=True
        mock_conn.execute.return_value = mock_result
        mock_engine = MagicMock()
        mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)

        with patch("civpulse_geo.cli.create_engine", return_value=mock_engine):
            result = runner.invoke(app, ["load-macon-bibb", str(geojson_file)])

        assert result.exit_code == 0
        assert "processed" in result.output.lower() or "import" in result.output.lower()


# ---------------------------------------------------------------------------
# _parse_macon_bibb_feature tests
# ---------------------------------------------------------------------------

class TestParseMaconBibbFeature:

    def test_valid_feature_parses_correctly(self):
        """Valid feature extracts all fields and computes source_hash."""
        from civpulse_geo.cli import _parse_macon_bibb_feature
        feat = {
            "properties": {
                "OBJECTID": 1,
                "ADDR_HN": "489",
                "ADDR_SN": "NORTHMINSTER",
                "ADDR_ST": "DR",
                "UNIT": " ",
                "City_1": "MACON",
                "ZIP_1": "31204",
                "ADDType": "PARCEL",
                "FULLADDR": "489 NORTHMINSTER DR",
            },
            "geometry": {"type": "Point", "coordinates": [-83.687, 32.872]},
        }
        stats = {"skipped": 0}
        result = _parse_macon_bibb_feature(feat, stats)

        assert result is not None
        assert result["street_number"] == "489"
        assert result["street_name"] == "NORTHMINSTER"
        assert result["street_suffix"] == "DR"
        assert result["city"] == "MACON"
        assert result["state"] == "GA"
        assert result["zip_code"] == "31204"
        assert result["address_type"] == "PARCEL"
        assert result["unit"] is None  # whitespace-only -> None
        assert result["source_hash"] != ""
        assert len(result["source_hash"]) == 64  # SHA-256 hex

    def test_missing_geometry_skips(self):
        from civpulse_geo.cli import _parse_macon_bibb_feature
        feat = {"properties": {"OBJECTID": 1, "FULLADDR": "X"}, "geometry": None}
        stats = {"skipped": 0}
        result = _parse_macon_bibb_feature(feat, stats)
        assert result is None
        assert stats["skipped"] == 1

    def test_missing_coordinates_skips(self):
        from civpulse_geo.cli import _parse_macon_bibb_feature
        feat = {
            "properties": {"OBJECTID": 1, "FULLADDR": "X"},
            "geometry": {"type": "Point", "coordinates": []},
        }
        stats = {"skipped": 0}
        result = _parse_macon_bibb_feature(feat, stats)
        assert result is None
        assert stats["skipped"] == 1

    def test_whitespace_only_fields_become_none(self):
        from civpulse_geo.cli import _parse_macon_bibb_feature
        feat = {
            "properties": {
                "OBJECTID": 2,
                "ADDR_HN": "  ",
                "ADDR_SN": "OAK",
                "ADDR_ST": "  ",
                "UNIT": " ",
                "City_1": "MACON",
                "ZIP_1": "31201",
                "ADDType": "PARCEL",
                "FULLADDR": "OAK ST",
            },
            "geometry": {"type": "Point", "coordinates": [-83.6, 32.8]},
        }
        stats = {"skipped": 0}
        result = _parse_macon_bibb_feature(feat, stats)
        assert result is not None
        assert result["street_number"] is None
        assert result["street_suffix"] is None
        assert result["unit"] is None

    def test_source_hash_is_sha256_of_objectid_fulladdr_coords(self):
        """source_hash matches SHA-256("{OBJECTID}:{FULLADDR}:{lon}:{lat}")."""
        import hashlib
        from civpulse_geo.cli import _parse_macon_bibb_feature
        feat = {
            "properties": {
                "OBJECTID": 1,
                "FULLADDR": "489 NORTHMINSTER DR",
                "City_1": "MACON",
                "ZIP_1": "31204",
            },
            "geometry": {"type": "Point", "coordinates": [-83.687, 32.872]},
        }
        stats = {"skipped": 0}
        result = _parse_macon_bibb_feature(feat, stats)

        expected = hashlib.sha256(
            f"1:489 NORTHMINSTER DR:{-83.687}:{32.872}".encode()
        ).hexdigest()
        assert result["source_hash"] == expected
