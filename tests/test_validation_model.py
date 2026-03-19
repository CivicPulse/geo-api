"""Unit tests for ValidationResult dataclass, ORM model, and Alembic migration.

TDD red phase — these tests will fail until Task 1 implementation is complete.

Tests verify:
- ValidationResult dataclass in providers/schemas.py has all 10 required fields
- ValidationResult ORM model creates table name "validation_results"
- ValidationResult ORM model has UniqueConstraint named "uq_validation_address_provider"
  on (address_id, provider_name)
"""
import inspect

import pytest
from dataclasses import fields

from civpulse_geo.providers.schemas import ValidationResult as ValidationResultDataclass
from civpulse_geo.models.validation import ValidationResult as ValidationResultORM
from civpulse_geo.models import ValidationResultORM as ValidationResultORMFromInit
from sqlalchemy import UniqueConstraint


class TestValidationResultDataclass:
    """Tests for the ValidationResult dataclass in providers/schemas.py."""

    def test_validation_result_dataclass_has_normalized_address(self):
        """ValidationResult dataclass has normalized_address field."""
        field_names = {f.name for f in fields(ValidationResultDataclass)}
        assert "normalized_address" in field_names

    def test_validation_result_dataclass_has_address_line_1(self):
        """ValidationResult dataclass has address_line_1 field."""
        field_names = {f.name for f in fields(ValidationResultDataclass)}
        assert "address_line_1" in field_names

    def test_validation_result_dataclass_has_address_line_2(self):
        """ValidationResult dataclass has address_line_2 field."""
        field_names = {f.name for f in fields(ValidationResultDataclass)}
        assert "address_line_2" in field_names

    def test_validation_result_dataclass_has_city(self):
        """ValidationResult dataclass has city field."""
        field_names = {f.name for f in fields(ValidationResultDataclass)}
        assert "city" in field_names

    def test_validation_result_dataclass_has_state(self):
        """ValidationResult dataclass has state field."""
        field_names = {f.name for f in fields(ValidationResultDataclass)}
        assert "state" in field_names

    def test_validation_result_dataclass_has_postal_code(self):
        """ValidationResult dataclass has postal_code field."""
        field_names = {f.name for f in fields(ValidationResultDataclass)}
        assert "postal_code" in field_names

    def test_validation_result_dataclass_has_confidence(self):
        """ValidationResult dataclass has confidence field."""
        field_names = {f.name for f in fields(ValidationResultDataclass)}
        assert "confidence" in field_names

    def test_validation_result_dataclass_has_delivery_point_verified(self):
        """ValidationResult dataclass has delivery_point_verified field."""
        field_names = {f.name for f in fields(ValidationResultDataclass)}
        assert "delivery_point_verified" in field_names

    def test_validation_result_dataclass_has_provider_name(self):
        """ValidationResult dataclass has provider_name field."""
        field_names = {f.name for f in fields(ValidationResultDataclass)}
        assert "provider_name" in field_names

    def test_validation_result_dataclass_has_original_input(self):
        """ValidationResult dataclass has original_input field."""
        field_names = {f.name for f in fields(ValidationResultDataclass)}
        assert "original_input" in field_names

    def test_validation_result_dataclass_has_exactly_10_fields(self):
        """ValidationResult dataclass has exactly 10 fields."""
        field_names = {f.name for f in fields(ValidationResultDataclass)}
        assert len(field_names) == 10

    def test_validation_result_dataclass_instantiation(self):
        """ValidationResult dataclass can be instantiated with all fields."""
        result = ValidationResultDataclass(
            normalized_address="123 MAIN ST MACON GA 31201",
            address_line_1="123 MAIN ST",
            address_line_2=None,
            city="MACON",
            state="GA",
            postal_code="31201",
            confidence=1.0,
            delivery_point_verified=False,
            provider_name="scourgify",
            original_input="123 Main St Macon GA 31201",
        )
        assert result.normalized_address == "123 MAIN ST MACON GA 31201"
        assert result.address_line_1 == "123 MAIN ST"
        assert result.address_line_2 is None
        assert result.city == "MACON"
        assert result.state == "GA"
        assert result.postal_code == "31201"
        assert result.confidence == 1.0
        assert result.delivery_point_verified is False
        assert result.provider_name == "scourgify"
        assert result.original_input == "123 Main St Macon GA 31201"


class TestValidationResultORM:
    """Tests for the ValidationResult ORM model in models/validation.py."""

    def test_orm_table_name(self):
        """ValidationResult ORM model has tablename 'validation_results'."""
        assert ValidationResultORM.__tablename__ == "validation_results"

    def test_orm_has_unique_constraint_name(self):
        """ValidationResult ORM model has UniqueConstraint named 'uq_validation_address_provider'."""
        constraint_names = {
            c.name
            for c in ValidationResultORM.__table_args__
            if isinstance(c, UniqueConstraint)
        }
        assert "uq_validation_address_provider" in constraint_names

    def test_orm_unique_constraint_columns(self):
        """UniqueConstraint covers address_id and provider_name columns."""
        for c in ValidationResultORM.__table_args__:
            if isinstance(c, UniqueConstraint) and c.name == "uq_validation_address_provider":
                # The columns are defined as strings in __table_args__; retrieve from table
                break
        # Verify via the table columns
        table = ValidationResultORM.__table__
        constraint = next(
            c for c in table.constraints
            if isinstance(c, UniqueConstraint) and c.name == "uq_validation_address_provider"
        )
        col_names = {col.name for col in constraint.columns}
        assert "address_id" in col_names
        assert "provider_name" in col_names

    def test_orm_has_address_id_fk(self):
        """ValidationResult ORM has address_id with FK to addresses.id."""
        col = ValidationResultORM.__table__.c["address_id"]
        fk_targets = {fk.target_fullname for fk in col.foreign_keys}
        assert "addresses.id" in fk_targets

    def test_orm_postal_code_is_string_10(self):
        """postal_code column is String(10) to accommodate ZIP+4."""
        col = ValidationResultORM.__table__.c["postal_code"]
        assert col.type.length == 10

    def test_orm_delivery_point_verified_is_boolean(self):
        """delivery_point_verified column is Boolean type."""
        from sqlalchemy import Boolean
        col = ValidationResultORM.__table__.c["delivery_point_verified"]
        assert isinstance(col.type, Boolean)

    def test_orm_exported_from_models_init(self):
        """ValidationResultORM is exported from civpulse_geo.models."""
        assert ValidationResultORMFromInit is ValidationResultORM


class TestAlembicMigration:
    """Tests for the Alembic migration file."""

    def test_migration_file_exists(self):
        """An Alembic migration file exists for validation_results."""
        import glob
        import os
        pattern = os.path.join(
            os.path.dirname(__file__),
            "..", "alembic", "versions", "*validation_results*.py"
        )
        matches = glob.glob(pattern)
        assert len(matches) >= 1, (
            "No Alembic migration file found matching *validation_results*.py "
            f"in alembic/versions/. Pattern: {pattern}"
        )

    def test_migration_creates_validation_results_table(self):
        """Migration upgrade creates the validation_results table."""
        import glob
        import os
        import importlib.util

        pattern = os.path.join(
            os.path.dirname(__file__),
            "..", "alembic", "versions", "*validation_results*.py"
        )
        migration_file = glob.glob(pattern)[0]
        spec = importlib.util.spec_from_file_location("migration", migration_file)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        source = open(migration_file).read()
        assert "create_table('validation_results'" in source, (
            "Migration upgrade must call op.create_table('validation_results', ...)"
        )

    def test_migration_no_postgis_extension_drops(self):
        """Migration does not reference PostGIS/TIGER extension tables."""
        import glob
        import os

        pattern = os.path.join(
            os.path.dirname(__file__),
            "..", "alembic", "versions", "*validation_results*.py"
        )
        migration_file = glob.glob(pattern)[0]
        source = open(migration_file).read()
        forbidden = [
            "spatial_ref_sys",
            "geography_columns",
            "geometry_columns",
            "tiger",
            "topology",
        ]
        for term in forbidden:
            assert term not in source, (
                f"Migration must not reference PostGIS extension table '{term}'. "
                "Remove all DROP statements for PostGIS extension tables."
            )

    def test_migration_chains_from_initial_schema(self):
        """Migration down_revision points to b98c26825b02 (initial schema)."""
        import glob
        import os

        pattern = os.path.join(
            os.path.dirname(__file__),
            "..", "alembic", "versions", "*validation_results*.py"
        )
        migration_file = glob.glob(pattern)[0]
        source = open(migration_file).read()
        assert "b98c26825b02" in source, (
            "Migration down_revision must reference 'b98c26825b02' (initial schema)."
        )
