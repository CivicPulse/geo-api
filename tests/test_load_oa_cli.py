"""Tests for PIPE-05: load-oa CLI command registration and help text."""
import gzip
import json
import unittest.mock as mock
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from civpulse_geo.cli import app
from civpulse_geo.cli import _parse_street_components, _parse_oa_feature, _upsert_oa_batch

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


class TestLoadOaImport:
    def test_parse_street_components_with_suffix(self):
        """_parse_street_components returns (name, suffix) for street with post-type."""
        name, suffix = _parse_street_components("MAIN ST")
        assert name == "MAIN"
        assert suffix == "ST"

    def test_parse_street_components_no_suffix(self):
        """_parse_street_components returns (full_street, None) when no StreetNamePostType found."""
        name, suffix = _parse_street_components("MANNING MILL")
        # usaddress may parse these as StreetName tokens — both words, no suffix
        assert suffix is None
        assert "MANNING" in name and "MILL" in name

    def test_parse_street_components_empty(self):
        """_parse_street_components handles empty string gracefully."""
        name, suffix = _parse_street_components("")
        assert name == ""
        assert suffix is None

    def test_parse_oa_feature_valid(self):
        """_parse_oa_feature returns correct dict for a valid GeoJSON feature."""
        feat = {
            "type": "Feature",
            "properties": {
                "hash": "abc123",
                "number": "123",
                "street": "MAIN ST",
                "unit": "",
                "city": "MACON",
                "district": "",
                "region": "GA",
                "postcode": "31201",
                "accuracy": "rooftop",
            },
            "geometry": {
                "type": "Point",
                "coordinates": [-83.63, 32.84],
            },
        }
        stats = {"processed": 0, "inserted": 0, "updated": 0, "skipped": 0}
        row = _parse_oa_feature(feat, stats)
        assert row is not None
        assert row["source_hash"] == "abc123"
        assert row["street_number"] == "123"
        assert row["city"] == "MACON"
        assert row["region"] == "GA"
        assert row["postcode"] == "31201"
        assert row["accuracy"] == "rooftop"
        assert "POINT" in row["location"]
        assert "-83.63" in row["location"]
        # Empty strings converted to None
        assert row["unit"] is None
        assert row["district"] is None

    def test_parse_oa_feature_missing_coordinates(self):
        """_parse_oa_feature returns None and increments skipped when coordinates missing."""
        feat = {
            "type": "Feature",
            "properties": {"hash": "abc123", "number": "123", "street": "MAIN ST"},
            "geometry": None,
        }
        stats = {"processed": 0, "inserted": 0, "updated": 0, "skipped": 0}
        result = _parse_oa_feature(feat, stats)
        assert result is None
        assert stats["skipped"] == 1

    def test_parse_oa_feature_empty_strings_to_none(self):
        """_parse_oa_feature converts empty string fields to None."""
        feat = {
            "type": "Feature",
            "properties": {
                "hash": "abc456",
                "number": "",
                "street": "OAK AVE",
                "unit": "",
                "city": "",
                "district": "",
                "region": "",
                "postcode": "",
                "accuracy": "",
            },
            "geometry": {"type": "Point", "coordinates": [-84.0, 33.0]},
        }
        stats = {"processed": 0, "inserted": 0, "updated": 0, "skipped": 0}
        row = _parse_oa_feature(feat, stats)
        assert row is not None
        assert row["street_number"] is None
        assert row["unit"] is None
        assert row["city"] is None
        assert row["district"] is None
        assert row["region"] is None
        assert row["postcode"] is None
        assert row["accuracy"] is None

    def test_parse_oa_feature_no_hash(self):
        """_parse_oa_feature returns None when hash property is missing or empty."""
        feat = {
            "type": "Feature",
            "properties": {
                "hash": "",
                "number": "123",
                "street": "MAIN ST",
            },
            "geometry": {"type": "Point", "coordinates": [-83.63, 32.84]},
        }
        stats = {"processed": 0, "inserted": 0, "updated": 0, "skipped": 0}
        result = _parse_oa_feature(feat, stats)
        assert result is None
        assert stats["skipped"] == 1

    def test_upsert_batch_mock_db(self):
        """_upsert_oa_batch calls execute with uq_oa_source_hash SQL and updates stats."""
        # Mock result where was_inserted = True
        mock_result = MagicMock()
        mock_result.scalar.return_value = True

        mock_conn = MagicMock()
        mock_conn.execute.return_value = mock_result

        batch = [
            {
                "source_hash": "abc123",
                "street_number": "123",
                "street_name": "MAIN",
                "street_suffix": "ST",
                "unit": None,
                "city": "MACON",
                "district": None,
                "region": "GA",
                "postcode": "31201",
                "location": "SRID=4326;POINT(-83.63 32.84)",
                "accuracy": "rooftop",
            }
        ]
        stats = {"processed": 0, "inserted": 0, "updated": 0, "skipped": 0}

        _upsert_oa_batch(mock_conn, batch, stats)

        # Verify execute was called
        assert mock_conn.execute.called
        # Verify commit was called
        assert mock_conn.commit.called
        # Verify stats updated
        assert stats["inserted"] == 1

        # Verify SQL contains key constraint
        call_args = mock_conn.execute.call_args
        sql_text = str(call_args[0][0])
        assert "uq_oa_source_hash" in sql_text

    def test_load_oa_with_mock_ndjson(self, tmp_path):
        """load-oa with a valid .geojson.gz file processes records and prints summary."""
        # Create a .geojson.gz file with 3 valid features + 1 malformed line
        geojson_lines = [
            json.dumps({
                "type": "Feature",
                "properties": {
                    "hash": f"hash{i}",
                    "number": str(100 + i),
                    "street": "MAIN ST",
                    "unit": "",
                    "city": "MACON",
                    "district": "",
                    "region": "GA",
                    "postcode": "31201",
                    "accuracy": "rooftop",
                },
                "geometry": {"type": "Point", "coordinates": [-83.63, 32.84]},
            })
            for i in range(3)
        ]
        # Add one malformed line
        all_lines = geojson_lines + ["{not valid json{{"]

        gz_path = tmp_path / "test.geojson.gz"
        with gzip.open(gz_path, "wt") as f:
            for line in all_lines:
                f.write(line + "\n")

        # Mock the database connection
        mock_result = MagicMock()
        mock_result.scalar.return_value = True  # was_inserted = True

        mock_conn = MagicMock()
        mock_conn.execute.return_value = mock_result
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)

        mock_engine = MagicMock()
        mock_engine.connect.return_value = mock_conn

        with patch("civpulse_geo.cli.create_engine", return_value=mock_engine):
            result = runner.invoke(app, ["load-oa", str(gz_path)])

        assert result.exit_code == 0, f"Expected exit code 0, got {result.exit_code}\n{result.output}"
        assert "Processed: 4" in result.output
        assert "Skipped:   1" in result.output
