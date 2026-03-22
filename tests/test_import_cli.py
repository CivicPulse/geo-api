"""Tests for the GIS data import CLI tool.

Tests cover:
- Parser functions: load_geojson, load_kml, load_shp
- CLI import command: provider name, upsert behavior, OfficialGeocoding auto-set
"""
from __future__ import annotations

import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

DATA_DIR = Path(__file__).parent.parent / "data"
GEOJSON_PATH = DATA_DIR / "SAMPLE_Address_Points.geojson"
KML_PATH = DATA_DIR / "SAMPLE_MBIT2017.DBO.AddressPoint.kml"


# ──────────────────────────────────────────────────────────────────────────────
# Parser tests
# ──────────────────────────────────────────────────────────────────────────────

class TestLoadGeoJSON:
    def test_load_geojson_returns_features(self):
        from civpulse_geo.cli.parsers import load_geojson

        features = load_geojson(GEOJSON_PATH)
        assert len(features) > 0

    def test_load_geojson_feature_schema(self):
        from civpulse_geo.cli.parsers import load_geojson

        features = load_geojson(GEOJSON_PATH)
        feat = features[0]
        assert "properties" in feat
        assert "geometry" in feat

    def test_load_geojson_feature_properties(self):
        from civpulse_geo.cli.parsers import load_geojson

        features = load_geojson(GEOJSON_PATH)
        feat = features[0]
        assert "FULLADDR" in feat["properties"]
        assert "City_1" in feat["properties"]
        assert "ZIP_1" in feat["properties"]

    def test_geojson_coordinates_wgs84(self):
        from civpulse_geo.cli.parsers import load_geojson

        features = load_geojson(GEOJSON_PATH)
        for feat in features:
            lng, lat = feat["geometry"]["coordinates"][:2]
            assert -180 <= lng <= 180, f"Longitude {lng} out of WGS84 range"
            assert -90 <= lat <= 90, f"Latitude {lat} out of WGS84 range"


class TestLoadKML:
    def test_load_kml_returns_features(self):
        from civpulse_geo.cli.parsers import load_kml

        features = load_kml(KML_PATH)
        assert len(features) > 0

    def test_load_kml_feature_schema(self):
        from civpulse_geo.cli.parsers import load_kml

        features = load_kml(KML_PATH)
        feat = features[0]
        assert "properties" in feat
        assert "geometry" in feat

    def test_kml_coordinates_wgs84(self):
        from civpulse_geo.cli.parsers import load_kml

        features = load_kml(KML_PATH)
        for feat in features:
            lng, lat = feat["geometry"]["coordinates"][:2]
            assert -85 <= lng <= -83, f"Bibb County KML lng {lng} unexpected"
            assert 32 <= lat <= 34, f"Bibb County KML lat {lat} unexpected"


class TestLoadSHP:
    @pytest.fixture
    def shp_path(self, tmp_path):
        zip_path = DATA_DIR / "SAMPLE_Address_Points.shp.zip"
        if not zip_path.exists():
            pytest.skip("SHP zip not found")
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(tmp_path)
        shp_files = list(tmp_path.glob("*.shp"))
        if not shp_files:
            pytest.skip("No .shp found in zip")
        return shp_files[0]

    def test_load_shp_returns_features(self, shp_path):
        from civpulse_geo.cli.parsers import load_shp

        features = load_shp(shp_path)
        assert len(features) > 0

    def test_shp_coordinates_reprojected(self, shp_path):
        from civpulse_geo.cli.parsers import load_shp

        features = load_shp(shp_path)
        for feat in features:
            lng, lat = feat["geometry"]["coordinates"][:2]
            assert -180 <= lng <= 180, f"SHP lng {lng} not reprojected to WGS84"
            assert -90 <= lat <= 90, f"SHP lat {lat} not reprojected to WGS84"
            # Should be near Bibb County, GA
            assert -85 <= lng <= -83, f"SHP lng {lng} not near Bibb County"
            assert 32 <= lat <= 34, f"SHP lat {lat} not near Bibb County"


class TestUnsupportedExtension:
    def test_load_geojson_wrong_extension(self):
        from civpulse_geo.cli.parsers import load_geojson

        with pytest.raises(ValueError, match="Unsupported"):
            load_geojson(Path("fake.csv"))


# ──────────────────────────────────────────────────────────────────────────────
# CLI command tests
# ──────────────────────────────────────────────────────────────────────────────

class TestImportGISCommand:
    """Tests for the import_gis CLI command.

    The Typer app has a single command registered as @app.command("import").
    When a Typer app has only one command, invoking the app directly passes
    arguments to that command — no subcommand name prefix needed.
    """

    def _make_mock_engine(self):
        """Build a mock SQLAlchemy engine that returns address id=1 from all execute calls."""
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_engine.return_value.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.return_value.connect.return_value.__exit__ = MagicMock(return_value=False)
        mock_result = MagicMock()
        # fetchone returns (id, was_inserted=True) — address upsert & geocoding upsert
        mock_result.fetchone.return_value = (1, True)
        mock_result.scalar_one_or_none.return_value = None  # no admin override
        mock_conn.execute.return_value = mock_result
        return mock_engine, mock_conn

    def test_import_geojson_cli_runs(self):
        """CLI import command accepts a GeoJSON file and completes."""
        from typer.testing import CliRunner
        from civpulse_geo.cli import app

        runner = CliRunner()
        mock_engine, mock_conn = self._make_mock_engine()

        with patch("civpulse_geo.cli.create_engine", mock_engine):
            result = runner.invoke(
                app,
                ["import", str(GEOJSON_PATH), "--database-url", "postgresql+psycopg2://test:test@localhost/test"],
            )
            assert result.exit_code == 0, f"CLI failed: {result.output}\n{result.exception}"
            output = result.output.lower()
            assert "total" in output or "import" in output or "complete" in output

    def test_import_provider_name_in_sql(self):
        """Imported records use provider_name='bibb_county_gis' by default."""
        from typer.testing import CliRunner
        from civpulse_geo.cli import app

        runner = CliRunner()
        mock_engine, mock_conn = self._make_mock_engine()

        with patch("civpulse_geo.cli.create_engine", mock_engine):
            result = runner.invoke(
                app,
                ["import", str(GEOJSON_PATH), "--database-url", "postgresql+psycopg2://test:test@localhost/test"],
            )
            assert result.exit_code == 0, f"CLI failed: {result.output}\n{result.exception}"
            # Verify that execute was called with SQL containing bibb_county_gis
            sql_calls = [str(c) for c in mock_conn.execute.call_args_list]
            assert any("bibb_county_gis" in s for s in sql_calls), (
                f"Expected 'bibb_county_gis' in SQL calls, got: {sql_calls[:3]}"
            )

    def test_import_unsupported_format(self):
        """Unsupported format exits with non-zero code."""
        from typer.testing import CliRunner
        from civpulse_geo.cli import app

        runner = CliRunner()
        result = runner.invoke(
            app,
            ["import", "fake.csv", "--database-url", "postgresql+psycopg2://test:test@localhost/test"],
        )
        assert result.exit_code != 0

    def test_import_skips_official_when_admin_override_exists(self):
        """When admin_overrides row exists for an address, CLI does NOT insert into official_geocoding."""
        from typer.testing import CliRunner
        from civpulse_geo.cli import app

        runner = CliRunner()
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_engine.return_value.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.return_value.connect.return_value.__exit__ = MagicMock(return_value=False)

        # Track call sequence to distinguish address upsert, geocoding upsert,
        # admin_overrides check, and official_geocoding insert
        call_count = {"n": 0}
        def execute_side_effect(stmt, params=None):
            call_count["n"] += 1
            result = MagicMock()

            sql_text = getattr(stmt, 'text', str(stmt))

            if "admin_overrides" in sql_text:
                # Return a row indicating admin override EXISTS
                result.fetchone.return_value = (99,)
                return result
            elif "official_geocoding" in sql_text:
                # This should NOT be reached when admin override exists
                pytest.fail("official_geocoding INSERT should not execute when admin_overrides row exists")
            else:
                # Address upsert or geocoding_results upsert
                result.fetchone.return_value = (1, True)
                return result

        mock_conn.execute.side_effect = execute_side_effect

        with patch("civpulse_geo.cli.create_engine", mock_engine):
            result = runner.invoke(
                app,
                ["import", str(GEOJSON_PATH), "--database-url", "postgresql+psycopg2://test:test@localhost/test"],
            )
            assert result.exit_code == 0, f"CLI failed: {result.output}\n{result.exception}"
