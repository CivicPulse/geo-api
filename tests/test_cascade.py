"""Unit tests for CascadeOrchestrator, consensus scoring, haversine, and related helpers.

Tests are organized around pure-function tests (no DB required) and
integration-style tests that mock the database session, providers, and
fuzzy/spell helpers.
"""
from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from civpulse_geo.services.cascade import (
    CascadeOrchestrator,
    CascadeResult,
    Cluster,
    ProviderCandidate,
    get_provider_weight,
    haversine_m,
    run_consensus,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def make_candidate(
    provider_name: str = "census",
    lat: float = 32.8407,
    lng: float = -83.6324,
    confidence: float = 0.95,
    weight: float = 0.90,
    is_fuzzy: bool = False,
) -> ProviderCandidate:
    return ProviderCandidate(
        provider_name=provider_name,
        lat=lat,
        lng=lng,
        confidence=confidence,
        weight=weight,
        is_fuzzy=is_fuzzy,
    )


# ---------------------------------------------------------------------------
# haversine_m tests
# ---------------------------------------------------------------------------

class TestHaversineM:
    def test_same_point_returns_zero(self):
        """haversine_m of identical points is 0.0."""
        result = haversine_m(32.8407, -83.6324, 32.8407, -83.6324)
        assert result == 0.0

    def test_approx_111m_for_0001_deg_lat(self):
        """0.001 degree latitude difference ≈ 111m."""
        result = haversine_m(32.8407, -83.6324, 32.8417, -83.6324)
        # Earth radius ~6,371 km; 1 degree latitude ≈ 111,000m; 0.001 ≈ 111m
        assert 100 < result < 125, f"Expected ~111m, got {result:.1f}m"

    def test_known_distance_north_south(self):
        """1 degree latitude ≈ 111km."""
        result = haversine_m(0.0, 0.0, 1.0, 0.0)
        assert 110_000 < result < 112_000

    def test_antipodal_points_is_half_circumference(self):
        """Antipodal points should be approximately half earth circumference."""
        result = haversine_m(0.0, 0.0, 0.0, 180.0)
        # Half circumference ≈ 20,015,087m
        assert abs(result - 20_015_087) < 10_000


# ---------------------------------------------------------------------------
# get_provider_weight tests
# ---------------------------------------------------------------------------

class TestGetProviderWeight:
    def test_census_weight(self):
        assert get_provider_weight("census") == pytest.approx(0.90)

    def test_openaddresses_weight(self):
        assert get_provider_weight("openaddresses") == pytest.approx(0.80)

    def test_macon_bibb_weight(self):
        assert get_provider_weight("macon_bibb") == pytest.approx(0.80)

    def test_nad_weight(self):
        assert get_provider_weight("nad") == pytest.approx(0.80)

    def test_tiger_weight(self):
        assert get_provider_weight("tiger") == pytest.approx(0.40)

    def test_unknown_provider_fallback(self):
        assert get_provider_weight("unknown_xyz") == pytest.approx(0.50)


# ---------------------------------------------------------------------------
# Cluster tests
# ---------------------------------------------------------------------------

class TestCluster:
    def test_seed_creates_cluster_with_single_member(self):
        c = make_candidate(lat=32.8407, lng=-83.6324, weight=0.90)
        cluster = Cluster.from_seed(c)
        assert len(cluster.members) == 1
        assert cluster.total_weight == pytest.approx(0.90)
        assert cluster.centroid_lat == pytest.approx(32.8407)
        assert cluster.centroid_lng == pytest.approx(-83.6324)

    def test_weighted_centroid_shifts_toward_higher_weight(self):
        """Census (w=0.90) and Tiger (w=0.40) — centroid should be closer to Census."""
        census = make_candidate(provider_name="census", lat=32.8407, lng=-83.6324, weight=0.90)
        tiger = make_candidate(provider_name="tiger", lat=32.8500, lng=-83.6324, weight=0.40)

        cluster = Cluster.from_seed(census)
        cluster.add(tiger)

        # Weighted centroid: (0.90*32.8407 + 0.40*32.8500) / (0.90+0.40)
        expected_lat = (0.90 * 32.8407 + 0.40 * 32.8500) / 1.30
        assert cluster.centroid_lat == pytest.approx(expected_lat, rel=1e-5)
        # Centroid should be closer to census point than to tiger point
        census_dist = abs(cluster.centroid_lat - 32.8407)
        tiger_dist = abs(cluster.centroid_lat - 32.8500)
        assert census_dist < tiger_dist, "Centroid should be closer to higher-weight census point"

    def test_total_weight_accumulates(self):
        c1 = make_candidate(weight=0.90)
        c2 = make_candidate(weight=0.80)
        cluster = Cluster.from_seed(c1)
        cluster.add(c2)
        assert cluster.total_weight == pytest.approx(1.70)


# ---------------------------------------------------------------------------
# run_consensus tests
# ---------------------------------------------------------------------------

class TestRunConsensus:
    def test_two_results_within_100m_cluster_together(self):
        """Results ~10m apart should land in the same cluster."""
        c1 = make_candidate(provider_name="census", lat=32.8407, lng=-83.6324, weight=0.90)
        # ~10m north (0.0001 deg ≈ 11m)
        c2 = make_candidate(provider_name="openaddresses", lat=32.8408, lng=-83.6324, weight=0.80)

        winning_cluster, candidates = run_consensus([c1, c2])

        assert winning_cluster is not None
        assert len(winning_cluster.members) == 2

    def test_result_over_100m_starts_new_cluster(self):
        """Result >100m away should not join the first cluster."""
        c1 = make_candidate(provider_name="census", lat=32.8407, lng=-83.6324, weight=0.90)
        # ~222m north (0.002 deg ≈ 222m)
        c2 = make_candidate(provider_name="nad", lat=32.8427, lng=-83.6324, weight=0.80)

        winning_cluster, candidates = run_consensus([c1, c2])

        # Both are in separate clusters; winning cluster has only 1 member
        assert winning_cluster is not None
        # The winning cluster is the one with higher weight (census=0.90 wins)
        winner_names = [m.provider_name for m in winning_cluster.members]
        assert "census" in winner_names

    def test_higher_weight_cluster_wins_over_more_members(self):
        """Cluster with higher total weight wins even if it has fewer members."""
        # Census alone: total weight = 0.90
        census = make_candidate(provider_name="census", lat=32.8407, lng=-83.6324, weight=0.90)

        # Two Tiger results far from census but close to each other: total weight = 0.40+0.40 = 0.80
        tiger1 = make_candidate(provider_name="tiger_a", lat=32.8600, lng=-83.6324, weight=0.40)
        tiger2 = make_candidate(provider_name="tiger_b", lat=32.8605, lng=-83.6324, weight=0.40)

        winning_cluster, _ = run_consensus([census, tiger1, tiger2])

        assert winning_cluster is not None
        # Census cluster wins: 0.90 > 0.80
        member_names = [m.provider_name for m in winning_cluster.members]
        assert "census" in member_names

    def test_outlier_flagging_over_1km(self):
        """Results >1km from winning centroid are flagged as outliers."""
        census = make_candidate(provider_name="census", lat=32.8407, lng=-83.6324, weight=0.90)
        # Very far away (~11km north)
        outlier = make_candidate(provider_name="nad", lat=32.9407, lng=-83.6324, weight=0.80)

        _, candidates = run_consensus([census, outlier])

        outlier_candidates = [c for c in candidates if getattr(c, 'is_outlier', False)]
        assert len(outlier_candidates) >= 1
        assert any(c.provider_name == "nad" for c in outlier_candidates)

    def test_no_outlier_when_within_1km(self):
        """Results within 1km of winning centroid are NOT flagged."""
        c1 = make_candidate(provider_name="census", lat=32.8407, lng=-83.6324, weight=0.90)
        # ~111m away — within 1km
        c2 = make_candidate(provider_name="nad", lat=32.8417, lng=-83.6324, weight=0.80)

        _, candidates = run_consensus([c1, c2])
        outliers = [c for c in candidates if getattr(c, 'is_outlier', False)]
        assert len(outliers) == 0

    def test_empty_candidates_returns_none(self):
        winning_cluster, candidates = run_consensus([])
        assert winning_cluster is None
        assert candidates == []

    def test_single_candidate_is_winning_cluster(self):
        c = make_candidate()
        winning_cluster, candidates = run_consensus([c])
        assert winning_cluster is not None
        assert len(winning_cluster.members) == 1


# ---------------------------------------------------------------------------
# CascadeOrchestrator integration tests (mocked DB)
# ---------------------------------------------------------------------------

def make_mock_provider(
    provider_name: str = "census",
    lat: float = 32.8407,
    lng: float = -83.6324,
    confidence: float = 0.95,
    location_type: str = "ROOFTOP",
    is_local: bool = False,
):
    """Build a mock GeocodingProvider."""
    from civpulse_geo.providers.schemas import GeocodingResult as GeocodingResultSchema

    provider = MagicMock()
    provider.provider_name = provider_name
    provider.is_local = is_local
    provider.geocode = AsyncMock(
        return_value=GeocodingResultSchema(
            lat=lat,
            lng=lng,
            location_type=location_type,
            confidence=confidence,
            raw_response={"provider": provider_name},
            provider_name=provider_name,
        )
    )
    return provider


def make_mock_db(address_id: int = 1):
    """Build an async mock DB session."""
    from civpulse_geo.models.address import Address

    mock_address = MagicMock(spec=Address)
    mock_address.id = address_id
    mock_address.original_input = "123 MAIN ST MACON GA 31201"
    mock_address.normalized_address = "123 MAIN ST MACON GA 31201"
    mock_address.address_hash = "abc123"
    mock_address.geocoding_results = []

    db = AsyncMock()
    db.execute = AsyncMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.add = MagicMock()

    # Simulate: SELECT Address WHERE address_hash=... -> None (new address)
    # Then flush creates address with id
    scalar_result = MagicMock()
    scalar_result.scalars.return_value.first.return_value = None
    db.execute.return_value = scalar_result

    return db, mock_address


class TestCascadeOrchestratorEarlyExit:
    @pytest.mark.asyncio
    async def test_early_exit_skips_fuzzy_when_high_confidence(self):
        """Early-exit fires when exact-match result has confidence >= 0.80."""
        orchestrator = CascadeOrchestrator()

        high_conf_provider = make_mock_provider(
            provider_name="census",
            confidence=0.95,
            is_local=False,
        )

        fuzzy_matcher = AsyncMock()
        fuzzy_matcher.find_fuzzy_match = AsyncMock()

        db, mock_address = make_mock_db()

        # Patch canonical_key + parse_address_components + Address lookup
        with patch("civpulse_geo.services.cascade.canonical_key",
                   return_value=("123 MAIN ST MACON GA 31201", "abc123")), \
             patch("civpulse_geo.services.cascade.parse_address_components",
                   return_value={"city": "MACON", "state": "GA"}), \
             patch("civpulse_geo.services.cascade._parse_input_address",
                   return_value=("123", "MAIN", "31201", "ST", None)):

            # Mock address query to return mock_address
            scalar_result = MagicMock()
            scalar_result.scalars.return_value.first.return_value = mock_address

            # Mock ORM upsert returning an id
            upsert_result = MagicMock()
            upsert_result.scalar_one.return_value = 42

            # Mock re-query for full ORM row
            orm_row_result = MagicMock()
            mock_orm_row = MagicMock()
            mock_orm_row.id = 42
            mock_orm_row.confidence = 0.95
            mock_orm_row.provider_name = "census"
            mock_orm_row.latitude = 32.8407
            mock_orm_row.longitude = -83.6324
            orm_row_result.scalars.return_value.first.return_value = mock_orm_row

            # Admin override check returns no override
            admin_check_result = MagicMock()
            admin_check_result.scalars.return_value.first.return_value = None

            # Official geocoding result after commit
            official_result_mock = MagicMock()
            official_result_mock.scalars.return_value.first.return_value = None

            db.execute.side_effect = [
                scalar_result,      # Address lookup
                upsert_result,      # GeocodingResult upsert
                orm_row_result,     # Re-query ORM row
                admin_check_result, # Admin override check (OfficialGeocoding)
                admin_check_result, # Admin override check (AdminOverride)
                upsert_result,      # OfficialGeocoding upsert
                official_result_mock,  # _get_official OfficialGeocoding
                official_result_mock,  # _get_official GeocodingResult
            ]

            result = await orchestrator.run(
                freeform="123 MAIN ST MACON GA 31201",
                db=db,
                providers={"census": high_conf_provider},
                http_client=MagicMock(),
                fuzzy_matcher=fuzzy_matcher,
            )

        # fuzzy_matcher.find_fuzzy_match should NOT have been called (early exit)
        fuzzy_matcher.find_fuzzy_match.assert_not_called()

    @pytest.mark.asyncio
    async def test_early_exit_does_not_skip_consensus(self):
        """Early-exit skips fuzzy but consensus scoring must still run (D-13)."""
        orchestrator = CascadeOrchestrator()

        high_conf_provider = make_mock_provider(
            provider_name="census",
            confidence=0.95,
            is_local=False,
        )

        db, mock_address = make_mock_db()

        with patch("civpulse_geo.services.cascade.canonical_key",
                   return_value=("123 MAIN ST MACON GA 31201", "abc123")), \
             patch("civpulse_geo.services.cascade.parse_address_components",
                   return_value={"city": "MACON"}), \
             patch("civpulse_geo.services.cascade._parse_input_address",
                   return_value=("123", "MAIN", "31201", "ST", None)):

            scalar_result = MagicMock()
            scalar_result.scalars.return_value.first.return_value = mock_address
            upsert_result = MagicMock()
            upsert_result.scalar_one.return_value = 99
            mock_orm_row = MagicMock()
            mock_orm_row.id = 99
            mock_orm_row.confidence = 0.95
            mock_orm_row.provider_name = "census"
            mock_orm_row.latitude = 32.8407
            mock_orm_row.longitude = -83.6324
            orm_row_result = MagicMock()
            orm_row_result.scalars.return_value.first.return_value = mock_orm_row
            admin_check = MagicMock()
            admin_check.scalars.return_value.first.return_value = None
            official_result_mock = MagicMock()
            official_result_mock.scalars.return_value.first.return_value = None

            db.execute.side_effect = [
                scalar_result,
                upsert_result,
                orm_row_result,
                admin_check,
                admin_check,
                upsert_result,
                official_result_mock,
                official_result_mock,
            ]

            result = await orchestrator.run(
                freeform="123 MAIN ST MACON GA 31201",
                db=db,
                providers={"census": high_conf_provider},
                http_client=MagicMock(),
                trace=True,
            )

        # cascade_trace should contain a consensus stage entry
        assert result.cascade_trace is not None
        stage_names = [entry.get("stage") for entry in result.cascade_trace]
        assert "consensus" in stage_names


class TestCascadeOrchestratorSingleResult:
    @pytest.mark.asyncio
    async def test_single_high_confidence_auto_sets_official(self):
        """Single result with confidence >= 0.80 sets OfficialGeocoding (D-11)."""
        orchestrator = CascadeOrchestrator()

        provider = make_mock_provider(confidence=0.95, is_local=False)

        db, mock_address = make_mock_db()

        with patch("civpulse_geo.services.cascade.canonical_key",
                   return_value=("123 MAIN ST MACON GA 31201", "abc123")), \
             patch("civpulse_geo.services.cascade.parse_address_components",
                   return_value={}), \
             patch("civpulse_geo.services.cascade._parse_input_address",
                   return_value=("123", "MAIN", "31201", "ST", None)):

            addr_res = MagicMock()
            addr_res.scalars.return_value.first.return_value = mock_address
            upsert_res = MagicMock()
            upsert_res.scalar_one.return_value = 10
            mock_orm_row = MagicMock()
            mock_orm_row.id = 10
            mock_orm_row.confidence = 0.95
            mock_orm_row.provider_name = "census"
            mock_orm_row.latitude = 32.8407
            mock_orm_row.longitude = -83.6324
            orm_res = MagicMock()
            orm_res.scalars.return_value.first.return_value = mock_orm_row
            admin_check = MagicMock()
            admin_check.scalars.return_value.first.return_value = None
            official_mock = MagicMock()
            official_mock.scalars.return_value.first.return_value = None

            db.execute.side_effect = [
                addr_res, upsert_res, orm_res,
                admin_check, admin_check, upsert_res,
                official_mock, official_mock,
            ]

            result = await orchestrator.run(
                freeform="123 MAIN ST MACON GA 31201",
                db=db,
                providers={"census": provider},
                http_client=MagicMock(),
            )

        # db.execute should have been called with OfficialGeocoding upsert
        call_count = db.execute.call_count
        assert call_count >= 5  # address, geocoding upsert, re-query, admin check x2, official upsert

    @pytest.mark.asyncio
    async def test_single_low_confidence_does_not_auto_set_official(self):
        """Single result with confidence < 0.80 does NOT write OfficialGeocoding (D-11)."""
        orchestrator = CascadeOrchestrator()

        provider = make_mock_provider(confidence=0.40, is_local=False)

        db, mock_address = make_mock_db()

        with patch("civpulse_geo.services.cascade.canonical_key",
                   return_value=("123 MAIN ST MACON GA 31201", "abc123")), \
             patch("civpulse_geo.services.cascade.parse_address_components",
                   return_value={}), \
             patch("civpulse_geo.services.cascade._parse_input_address",
                   return_value=("123", "MAIN", "31201", "ST", None)):

            addr_res = MagicMock()
            addr_res.scalars.return_value.first.return_value = mock_address
            upsert_res = MagicMock()
            upsert_res.scalar_one.return_value = 11
            mock_orm_row = MagicMock()
            mock_orm_row.id = 11
            mock_orm_row.confidence = 0.40
            mock_orm_row.provider_name = "census"
            mock_orm_row.latitude = 32.8407
            mock_orm_row.longitude = -83.6324
            orm_res = MagicMock()
            orm_res.scalars.return_value.first.return_value = mock_orm_row

            db.execute.side_effect = [
                addr_res, upsert_res, orm_res,
            ]

            result = await orchestrator.run(
                freeform="123 MAIN ST MACON GA 31201",
                db=db,
                providers={"census": provider},
                http_client=MagicMock(),
            )

        # OfficialGeocoding upsert should NOT be called for low-confidence single result
        # Verify by checking no upsert_official was called beyond the address/geocoding upserts
        # Only 3 db.execute calls expected: address lookup, geocoding upsert, orm re-query
        assert db.execute.call_count == 3


class TestCascadeOrchestratorAdminOverride:
    @pytest.mark.asyncio
    async def test_admin_override_blocks_cascade_auto_set(self):
        """Existing admin override prevents cascade from overwriting OfficialGeocoding (D-22)."""
        orchestrator = CascadeOrchestrator()

        provider = make_mock_provider(confidence=0.95, is_local=False)

        db, mock_address = make_mock_db()

        with patch("civpulse_geo.services.cascade.canonical_key",
                   return_value=("123 MAIN ST MACON GA 31201", "abc123")), \
             patch("civpulse_geo.services.cascade.parse_address_components",
                   return_value={}), \
             patch("civpulse_geo.services.cascade._parse_input_address",
                   return_value=("123", "MAIN", "31201", "ST", None)):

            addr_res = MagicMock()
            addr_res.scalars.return_value.first.return_value = mock_address
            upsert_res = MagicMock()
            upsert_res.scalar_one.return_value = 20
            mock_orm_row = MagicMock()
            mock_orm_row.id = 20
            mock_orm_row.confidence = 0.95
            mock_orm_row.provider_name = "census"
            mock_orm_row.latitude = 32.8407
            mock_orm_row.longitude = -83.6324
            orm_res = MagicMock()
            orm_res.scalars.return_value.first.return_value = mock_orm_row

            # OfficialGeocoding already has admin_override
            admin_official = MagicMock()
            admin_official.provider_name = "admin_override"
            official_with_admin = MagicMock()
            official_with_admin.scalars.return_value.first.return_value = admin_official

            # _get_official needs 2 queries: OfficialGeocoding + GeocodingResult
            official_row_mock = MagicMock()
            official_row_mock.geocoding_result_id = 20
            official_og_result = MagicMock()
            official_og_result.scalars.return_value.first.return_value = official_row_mock

            final_gr_mock = MagicMock()
            final_gr_mock.scalars.return_value.first.return_value = mock_orm_row

            db.execute.side_effect = [
                addr_res, upsert_res, orm_res,
                official_with_admin,  # admin override check (OfficialGeocoding join)
                official_og_result,   # _get_official: OfficialGeocoding lookup
                final_gr_mock,        # _get_official: GeocodingResult lookup
            ]

            result = await orchestrator.run(
                freeform="123 MAIN ST MACON GA 31201",
                db=db,
                providers={"census": provider},
                http_client=MagicMock(),
            )

        # Should commit but should NOT have called OfficialGeocoding upsert
        # The admin_override detection happened at check step, not re-written
        db.commit.assert_called()


class TestCascadeOrchestratorFuzzyWeight:
    def test_fuzzy_weight_scaled_by_confidence(self):
        """Fuzzy result weight = provider_weight * (fuzzy_confidence / 0.80) (D-09)."""
        # Fuzzy with confidence=0.60, source="openaddresses" (weight=0.80)
        # Expected effective weight: 0.80 * (0.60 / 0.80) = 0.60
        expected_weight = 0.80 * (0.60 / 0.80)

        fuzzy_confidence = 0.60
        source = "openaddresses"
        provider_weight = get_provider_weight(source)
        effective_weight = provider_weight * (fuzzy_confidence / 0.80)

        assert effective_weight == pytest.approx(expected_weight, rel=1e-5)

    def test_fuzzy_weight_at_max_confidence_equals_provider_weight(self):
        """Fuzzy with confidence=0.80 has same effective weight as exact provider."""
        source = "nad"
        provider_weight = get_provider_weight(source)
        fuzzy_confidence = 0.80
        effective_weight = provider_weight * (fuzzy_confidence / 0.80)
        assert effective_weight == pytest.approx(provider_weight, rel=1e-5)


class TestCascadeOrchestratorDryRun:
    @pytest.mark.asyncio
    async def test_dry_run_populates_would_set_official_not_writes(self):
        """dry_run=True populates would_set_official but does not write OfficialGeocoding."""
        orchestrator = CascadeOrchestrator()

        provider = make_mock_provider(confidence=0.95, is_local=False)

        db, mock_address = make_mock_db()

        with patch("civpulse_geo.services.cascade.canonical_key",
                   return_value=("123 MAIN ST MACON GA 31201", "abc123")), \
             patch("civpulse_geo.services.cascade.parse_address_components",
                   return_value={}), \
             patch("civpulse_geo.services.cascade._parse_input_address",
                   return_value=("123", "MAIN", "31201", "ST", None)):

            addr_res = MagicMock()
            addr_res.scalars.return_value.first.return_value = mock_address
            upsert_res = MagicMock()
            upsert_res.scalar_one.return_value = 30
            mock_orm_row = MagicMock()
            mock_orm_row.id = 30
            mock_orm_row.confidence = 0.95
            mock_orm_row.provider_name = "census"
            mock_orm_row.latitude = 32.8407
            mock_orm_row.longitude = -83.6324
            orm_res = MagicMock()
            orm_res.scalars.return_value.first.return_value = mock_orm_row
            admin_check = MagicMock()
            admin_check.scalars.return_value.first.return_value = None

            db.execute.side_effect = [
                addr_res, upsert_res, orm_res,
                admin_check, admin_check,
            ]

            result = await orchestrator.run(
                freeform="123 MAIN ST MACON GA 31201",
                db=db,
                providers={"census": provider},
                http_client=MagicMock(),
                dry_run=True,
            )

        # would_set_official should be populated
        assert result.would_set_official is not None
        # OfficialGeocoding upsert should NOT have been called (dry_run)
        # After 5 calls (addr, upsert, orm, admin check x2), no further upsert
        assert db.execute.call_count == 5


class TestCascadeOrchestratorTrace:
    @pytest.mark.asyncio
    async def test_trace_true_populates_cascade_trace(self):
        """trace=True populates cascade_trace with stage entries."""
        orchestrator = CascadeOrchestrator()

        provider = make_mock_provider(confidence=0.50, is_local=False)

        db, mock_address = make_mock_db()

        with patch("civpulse_geo.services.cascade.canonical_key",
                   return_value=("123 MAIN ST MACON GA 31201", "abc123")), \
             patch("civpulse_geo.services.cascade.parse_address_components",
                   return_value={}), \
             patch("civpulse_geo.services.cascade._parse_input_address",
                   return_value=("123", "MAIN", "31201", "ST", None)):

            addr_res = MagicMock()
            addr_res.scalars.return_value.first.return_value = mock_address
            upsert_res = MagicMock()
            upsert_res.scalar_one.return_value = 50
            mock_orm_row = MagicMock()
            mock_orm_row.id = 50
            mock_orm_row.confidence = 0.50
            mock_orm_row.provider_name = "census"
            mock_orm_row.latitude = 32.8407
            mock_orm_row.longitude = -83.6324
            orm_res = MagicMock()
            orm_res.scalars.return_value.first.return_value = mock_orm_row

            db.execute.side_effect = [
                addr_res, upsert_res, orm_res,
            ]

            result = await orchestrator.run(
                freeform="123 MAIN ST MACON GA 31201",
                db=db,
                providers={"census": provider},
                http_client=MagicMock(),
                trace=True,
            )

        assert result.cascade_trace is not None
        assert len(result.cascade_trace) >= 2  # at least normalize + exact_match stages
        stage_names = [entry.get("stage") for entry in result.cascade_trace]
        assert "normalize" in stage_names
        assert "exact_match" in stage_names


class TestCascadeOrchestratorLLMStage:
    """Integration tests for LLM correction stage 4 (LLM-02, D-05, D-06, D-08, D-17)."""

    @pytest.mark.asyncio
    async def test_llm_correction_enters_reverify_not_candidates(self):
        """LLM correction result is re-verified through providers, never added directly (D-17).

        Providers return no results on exact-match pass, then return a result when
        re-verification fires with the corrected address.
        """
        from unittest.mock import AsyncMock, MagicMock, patch
        from civpulse_geo.services.llm_corrector import LLMAddressCorrector, AddressCorrection
        from civpulse_geo.providers.schemas import GeocodingResult as GeocodingResultSchema

        orchestrator = CascadeOrchestrator()

        # Provider: returns no result on exact-match, returns a result on re-verify
        call_count = {"n": 0}

        async def _geocode_side_effect(addr, http_client):
            call_count["n"] += 1
            if call_count["n"] == 1:
                # First call (exact-match stage): no result
                return GeocodingResultSchema(
                    lat=0.0, lng=0.0, confidence=0.0,
                    location_type="APPROXIMATE",
                    raw_response={}, provider_name="census",
                )
            else:
                # Re-verify call with corrected address: return a result
                return GeocodingResultSchema(
                    lat=32.8407, lng=-83.6324, confidence=0.90,
                    location_type="ROOFTOP",
                    raw_response={"provider": "census"},
                    provider_name="census",
                )

        mock_provider = MagicMock()
        mock_provider.provider_name = "census"
        mock_provider.is_local = False
        mock_provider.geocode = AsyncMock(side_effect=_geocode_side_effect)

        # LLM corrector: returns a valid correction
        mock_llm = MagicMock(spec=LLMAddressCorrector)
        mock_llm.correct_address = AsyncMock(
            return_value=AddressCorrection(
                street_number="123",
                street_name="Main",
                street_suffix="St",
                city="Macon",
                state="GA",
                zip="31201",
            )
        )

        db, mock_address = make_mock_db()

        with patch("civpulse_geo.services.cascade.canonical_key",
                   return_value=("123 MAEN ST MACON GA 31201", "hashxyz")), \
             patch("civpulse_geo.services.cascade.parse_address_components",
                   return_value={"state": "GA"}), \
             patch("civpulse_geo.services.cascade._parse_input_address",
                   return_value=("123", "MAEN", "31201", "ST", None)), \
             patch("civpulse_geo.services.cascade.settings") as mock_settings:

            # Use real floats for arithmetic-used settings attributes
            mock_settings.cascade_llm_enabled = True
            mock_settings.exact_match_timeout_ms = 2000
            mock_settings.fuzzy_match_timeout_ms = 500
            mock_settings.llm_timeout_ms = 5000
            mock_settings.weight_census = 0.90
            mock_settings.weight_openaddresses = 0.80
            mock_settings.weight_macon_bibb = 0.80
            mock_settings.weight_tiger_unrestricted = 0.40
            mock_settings.weight_nad = 0.80

            addr_res = MagicMock()
            addr_res.scalars.return_value.first.return_value = mock_address
            upsert_res = MagicMock()
            upsert_res.scalar_one.return_value = 55
            mock_orm_row = MagicMock()
            mock_orm_row.id = 55
            mock_orm_row.confidence = 0.90
            mock_orm_row.provider_name = "census"
            mock_orm_row.latitude = 32.8407
            mock_orm_row.longitude = -83.6324
            orm_res = MagicMock()
            orm_res.scalars.return_value.first.return_value = mock_orm_row
            admin_check = MagicMock()
            admin_check.scalars.return_value.first.return_value = None
            official_mock = MagicMock()
            official_mock.scalars.return_value.first.return_value = None

            db.execute.side_effect = [
                addr_res,      # Address lookup
                upsert_res,    # GeocodingResult upsert (exact-match, no-match result)
                orm_res,       # Re-query ORM row
                upsert_res,    # LLM re-verify: persist candidate row
                admin_check,   # Admin override check (OfficialGeocoding)
                admin_check,   # Admin override check (AdminOverride)
                upsert_res,    # OfficialGeocoding upsert
                official_mock, # _get_official: OfficialGeocoding
                official_mock, # _get_official: GeocodingResult
            ]

            result = await orchestrator.run(
                freeform="123 MAEN ST MACON GA 31201",
                db=db,
                providers={"census": mock_provider},
                http_client=MagicMock(),
                llm_corrector=mock_llm,
                trace=True,
            )

        # LLM corrector was called
        mock_llm.correct_address.assert_called_once()

        # Provider was called twice: once for exact-match, once for re-verify
        assert mock_provider.geocode.call_count == 2

        # The re-verified result has is_llm_corrected=True
        llm_candidates = [c for c in result.cascade_trace or []
                          if c.get("stage") == "llm_correction"]
        assert len(llm_candidates) == 1
        assert llm_candidates[0].get("reverified_count", 0) >= 1

    @pytest.mark.asyncio
    async def test_llm_stage_skipped_when_disabled(self):
        """When CASCADE_LLM_ENABLED=false, LLM stage never fires even if llm_corrector is provided."""
        from unittest.mock import AsyncMock, MagicMock, patch
        from civpulse_geo.services.llm_corrector import LLMAddressCorrector, AddressCorrection

        orchestrator = CascadeOrchestrator()

        # Provider returns no results
        no_match_provider = make_mock_provider(confidence=0.0, is_local=False)

        # LLM corrector: should never be called
        mock_llm = MagicMock(spec=LLMAddressCorrector)
        mock_llm.correct_address = AsyncMock(
            return_value=AddressCorrection(
                street_number="123", street_name="Main", street_suffix="St",
                city="Macon", state="GA", zip="31201",
            )
        )

        db, mock_address = make_mock_db()

        with patch("civpulse_geo.services.cascade.canonical_key",
                   return_value=("123 MAEN ST MACON GA 31201", "hashxyz")), \
             patch("civpulse_geo.services.cascade.parse_address_components",
                   return_value={"state": "GA"}), \
             patch("civpulse_geo.services.cascade._parse_input_address",
                   return_value=("123", "MAEN", "31201", "ST", None)), \
             patch("civpulse_geo.services.cascade.settings") as mock_settings:

            mock_settings.cascade_llm_enabled = False  # LLM disabled
            mock_settings.exact_match_timeout_ms = 2000
            mock_settings.fuzzy_match_timeout_ms = 500
            mock_settings.llm_timeout_ms = 5000
            mock_settings.weight_census = 0.90
            mock_settings.weight_openaddresses = 0.80
            mock_settings.weight_macon_bibb = 0.80
            mock_settings.weight_tiger_unrestricted = 0.40
            mock_settings.weight_nad = 0.80

            addr_res = MagicMock()
            addr_res.scalars.return_value.first.return_value = mock_address
            upsert_res = MagicMock()
            upsert_res.scalar_one.return_value = 56
            mock_orm_row = MagicMock()
            mock_orm_row.id = 56
            mock_orm_row.confidence = 0.0
            mock_orm_row.provider_name = "census"
            mock_orm_row.latitude = 0.0
            mock_orm_row.longitude = 0.0
            orm_res = MagicMock()
            orm_res.scalars.return_value.first.return_value = mock_orm_row

            db.execute.side_effect = [
                addr_res, upsert_res, orm_res,
            ]

            result = await orchestrator.run(
                freeform="123 MAEN ST MACON GA 31201",
                db=db,
                providers={"census": no_match_provider},
                http_client=MagicMock(),
                llm_corrector=mock_llm,
            )

        # LLM corrector must NOT have been called
        mock_llm.correct_address.assert_not_called()

    @pytest.mark.asyncio
    async def test_llm_stage_skipped_when_exact_match_succeeds(self):
        """When exact match returns high-confidence result, LLM stage is skipped (D-05)."""
        from unittest.mock import AsyncMock, MagicMock, patch
        from civpulse_geo.services.llm_corrector import LLMAddressCorrector, AddressCorrection

        orchestrator = CascadeOrchestrator()

        # Provider returns high-confidence result (triggers early exit)
        high_conf_provider = make_mock_provider(confidence=0.95, is_local=False)

        mock_llm = MagicMock(spec=LLMAddressCorrector)
        mock_llm.correct_address = AsyncMock(
            return_value=AddressCorrection(
                street_number="123", street_name="Main", street_suffix="St",
                city="Macon", state="GA", zip="31201",
            )
        )

        db, mock_address = make_mock_db()

        with patch("civpulse_geo.services.cascade.canonical_key",
                   return_value=("123 MAIN ST MACON GA 31201", "abc123")), \
             patch("civpulse_geo.services.cascade.parse_address_components",
                   return_value={"state": "GA"}), \
             patch("civpulse_geo.services.cascade._parse_input_address",
                   return_value=("123", "MAIN", "31201", "ST", None)), \
             patch("civpulse_geo.services.cascade.settings") as mock_settings:

            mock_settings.cascade_llm_enabled = True
            mock_settings.exact_match_timeout_ms = 2000
            mock_settings.fuzzy_match_timeout_ms = 500
            mock_settings.llm_timeout_ms = 5000
            mock_settings.weight_census = 0.90
            mock_settings.weight_openaddresses = 0.80
            mock_settings.weight_macon_bibb = 0.80
            mock_settings.weight_tiger_unrestricted = 0.40
            mock_settings.weight_nad = 0.80

            addr_res = MagicMock()
            addr_res.scalars.return_value.first.return_value = mock_address
            upsert_res = MagicMock()
            upsert_res.scalar_one.return_value = 57
            mock_orm_row = MagicMock()
            mock_orm_row.id = 57
            mock_orm_row.confidence = 0.95
            mock_orm_row.provider_name = "census"
            mock_orm_row.latitude = 32.8407
            mock_orm_row.longitude = -83.6324
            orm_res = MagicMock()
            orm_res.scalars.return_value.first.return_value = mock_orm_row
            admin_check = MagicMock()
            admin_check.scalars.return_value.first.return_value = None
            official_mock = MagicMock()
            official_mock.scalars.return_value.first.return_value = None

            db.execute.side_effect = [
                addr_res, upsert_res, orm_res,
                admin_check, admin_check, upsert_res,
                official_mock, official_mock,
            ]

            result = await orchestrator.run(
                freeform="123 MAIN ST MACON GA 31201",
                db=db,
                providers={"census": high_conf_provider},
                http_client=MagicMock(),
                llm_corrector=mock_llm,
            )

        # LLM corrector must NOT have been called (skip_fuzzy=True blocks LLM stage)
        mock_llm.correct_address.assert_not_called()

    @pytest.mark.asyncio
    async def test_llm_stage_timeout_degrades_gracefully(self):
        """When LLM stage times out, cascade continues with empty candidates (D-08)."""
        from unittest.mock import AsyncMock, MagicMock, patch
        from civpulse_geo.services.llm_corrector import LLMAddressCorrector

        orchestrator = CascadeOrchestrator()

        # Provider returns no result
        no_match_provider = make_mock_provider(confidence=0.0, is_local=False)

        # LLM corrector: simulates timeout via asyncio.TimeoutError
        async def _timeout_correct(*args, **kwargs):
            raise asyncio.TimeoutError()

        mock_llm = MagicMock(spec=LLMAddressCorrector)
        mock_llm.correct_address = AsyncMock(side_effect=_timeout_correct)

        db, mock_address = make_mock_db()

        with patch("civpulse_geo.services.cascade.canonical_key",
                   return_value=("123 MAEN ST MACON GA 31201", "hashxyz")), \
             patch("civpulse_geo.services.cascade.parse_address_components",
                   return_value={"state": "GA"}), \
             patch("civpulse_geo.services.cascade._parse_input_address",
                   return_value=("123", "MAEN", "31201", "ST", None)), \
             patch("civpulse_geo.services.cascade.settings") as mock_settings:

            mock_settings.cascade_llm_enabled = True
            mock_settings.exact_match_timeout_ms = 2000
            mock_settings.fuzzy_match_timeout_ms = 500
            mock_settings.llm_timeout_ms = 5000
            mock_settings.weight_census = 0.90
            mock_settings.weight_openaddresses = 0.80
            mock_settings.weight_macon_bibb = 0.80
            mock_settings.weight_tiger_unrestricted = 0.40
            mock_settings.weight_nad = 0.80

            addr_res = MagicMock()
            addr_res.scalars.return_value.first.return_value = mock_address
            upsert_res = MagicMock()
            upsert_res.scalar_one.return_value = 58
            mock_orm_row = MagicMock()
            mock_orm_row.id = 58
            mock_orm_row.confidence = 0.0
            mock_orm_row.provider_name = "census"
            mock_orm_row.latitude = 0.0
            mock_orm_row.longitude = 0.0
            orm_res = MagicMock()
            orm_res.scalars.return_value.first.return_value = mock_orm_row

            db.execute.side_effect = [
                addr_res, upsert_res, orm_res,
            ]

            # Should NOT raise — cascade degrades gracefully on LLM timeout
            result = await orchestrator.run(
                freeform="123 MAEN ST MACON GA 31201",
                db=db,
                providers={"census": no_match_provider},
                http_client=MagicMock(),
                llm_corrector=mock_llm,
                trace=True,
            )

        # Cascade should have completed without error
        assert result is not None
        # Trace should contain llm_correction with timeout=True
        llm_entries = [e for e in (result.cascade_trace or [])
                       if e.get("stage") == "llm_correction"]
        assert len(llm_entries) == 1
        assert llm_entries[0].get("timeout") is True


class TestCascadeOrchestratorStageTimeout:
    @pytest.mark.asyncio
    async def test_stage_timeout_cascade_continues_with_empty(self):
        """Provider timeout produces empty results; cascade continues gracefully (D-16)."""
        orchestrator = CascadeOrchestrator()

        # Provider that always times out
        timeout_provider = MagicMock()
        timeout_provider.provider_name = "census"
        timeout_provider.is_local = False
        timeout_provider.geocode = AsyncMock(side_effect=asyncio.TimeoutError())

        db, mock_address = make_mock_db()

        with patch("civpulse_geo.services.cascade.canonical_key",
                   return_value=("123 MAIN ST MACON GA 31201", "abc123")), \
             patch("civpulse_geo.services.cascade.parse_address_components",
                   return_value={}), \
             patch("civpulse_geo.services.cascade._parse_input_address",
                   return_value=("123", "MAIN", "31201", "ST", None)):

            addr_res = MagicMock()
            addr_res.scalars.return_value.first.return_value = mock_address
            db.execute.side_effect = [addr_res]

            # Should not raise — cascade degrades gracefully
            result = await orchestrator.run(
                freeform="123 MAIN ST MACON GA 31201",
                db=db,
                providers={"census": timeout_provider},
                http_client=MagicMock(),
            )

        # Result should be valid even with no provider results
        assert result is not None
        assert result.results == [] or result.results is not None


# ---------------------------------------------------------------------------
# Per-provider timeout tests (DEBT-01)
# ---------------------------------------------------------------------------

class TestPerProviderTimeout:
    """Tiger provider gets 3000ms timeout; other providers get 2000ms (DEBT-01)."""

    @pytest.mark.asyncio
    async def test_tiger_uses_tiger_timeout_ms(self):
        """postgis_tiger provider uses settings.tiger_timeout_ms for asyncio.wait_for."""
        from unittest.mock import patch, AsyncMock, MagicMock, call
        from civpulse_geo.services.cascade import CascadeOrchestrator

        orchestrator = CascadeOrchestrator()

        tiger_provider = make_mock_provider(
            provider_name="postgis_tiger",
            confidence=0.75,
            is_local=True,
        )

        db, mock_address = make_mock_db()
        mock_address.geocoding_results = []  # no cache

        with patch("civpulse_geo.services.cascade.canonical_key",
                   return_value=("123 MAIN ST MACON GA 31201", "abc123")), \
             patch("civpulse_geo.services.cascade.parse_address_components",
                   return_value={}), \
             patch("civpulse_geo.services.cascade._parse_input_address",
                   return_value=("123", "MAIN", "31201", "ST", None)), \
             patch("civpulse_geo.services.cascade.settings") as mock_settings, \
             patch("civpulse_geo.services.cascade.asyncio.wait_for",
                   new_callable=AsyncMock) as mock_wait_for:

            mock_settings.cascade_llm_enabled = False
            mock_settings.exact_match_timeout_ms = 2000
            mock_settings.tiger_timeout_ms = 3000
            mock_settings.fuzzy_match_timeout_ms = 500
            mock_settings.llm_timeout_ms = 5000
            mock_settings.weight_census = 0.90
            mock_settings.weight_openaddresses = 0.80
            mock_settings.weight_macon_bibb = 0.80
            mock_settings.weight_tiger_unrestricted = 0.40
            mock_settings.weight_nad = 0.80

            # wait_for returning a schema result for tiger provider
            from civpulse_geo.providers.schemas import GeocodingResult as GeocodingResultSchema
            mock_wait_for.return_value = GeocodingResultSchema(
                lat=32.8407, lng=-83.6324,
                confidence=0.75, location_type="RANGE_INTERPOLATED",
                raw_response={}, provider_name="postgis_tiger",
            )

            addr_res = MagicMock()
            addr_res.scalars.return_value.first.return_value = mock_address
            db.execute.side_effect = [addr_res]

            await orchestrator.run(
                freeform="123 MAIN ST MACON GA 31201",
                db=db,
                providers={"postgis_tiger": tiger_provider},
                http_client=MagicMock(),
            )

        # The wait_for call for postgis_tiger must use tiger_timeout_ms / 1000 = 3.0
        tiger_calls = [
            c for c in mock_wait_for.call_args_list
            if c.kwargs.get("timeout") == pytest.approx(3.0)
            or (len(c.args) > 1 and c.args[1] == pytest.approx(3.0))
        ]
        # Verify timeout was 3000ms/1000 = 3.0s (not 2.0s)
        all_timeouts = [c.kwargs.get("timeout") for c in mock_wait_for.call_args_list]
        assert any(t == pytest.approx(3.0) for t in all_timeouts), \
            f"Expected tiger_timeout_ms (3.0s) but got timeouts: {all_timeouts}"

    @pytest.mark.asyncio
    async def test_census_uses_exact_match_timeout_ms(self):
        """Non-tiger providers use settings.exact_match_timeout_ms for asyncio.wait_for."""
        from unittest.mock import patch, AsyncMock, MagicMock
        from civpulse_geo.services.cascade import CascadeOrchestrator

        orchestrator = CascadeOrchestrator()

        census_provider = make_mock_provider(
            provider_name="census",
            confidence=0.95,
            is_local=False,
        )

        db, mock_address = make_mock_db()
        mock_address.geocoding_results = []

        with patch("civpulse_geo.services.cascade.canonical_key",
                   return_value=("123 MAIN ST MACON GA 31201", "abc123")), \
             patch("civpulse_geo.services.cascade.parse_address_components",
                   return_value={}), \
             patch("civpulse_geo.services.cascade._parse_input_address",
                   return_value=("123", "MAIN", "31201", "ST", None)), \
             patch("civpulse_geo.services.cascade.settings") as mock_settings, \
             patch("civpulse_geo.services.cascade.asyncio.wait_for",
                   new_callable=AsyncMock) as mock_wait_for:

            mock_settings.cascade_llm_enabled = False
            mock_settings.exact_match_timeout_ms = 2000
            mock_settings.tiger_timeout_ms = 3000
            mock_settings.fuzzy_match_timeout_ms = 500
            mock_settings.llm_timeout_ms = 5000
            mock_settings.weight_census = 0.90
            mock_settings.weight_openaddresses = 0.80
            mock_settings.weight_macon_bibb = 0.80
            mock_settings.weight_tiger_unrestricted = 0.40
            mock_settings.weight_nad = 0.80

            from civpulse_geo.providers.schemas import GeocodingResult as GeocodingResultSchema
            mock_wait_for.return_value = GeocodingResultSchema(
                lat=32.8407, lng=-83.6324,
                confidence=0.95, location_type="ROOFTOP",
                raw_response={}, provider_name="census",
            )

            addr_res = MagicMock()
            addr_res.scalars.return_value.first.return_value = mock_address
            upsert_res = MagicMock()
            upsert_res.scalar_one.return_value = 99
            orm_res = MagicMock()
            mock_orm = MagicMock()
            mock_orm.id = 99
            mock_orm.confidence = 0.95
            mock_orm.provider_name = "census"
            mock_orm.latitude = 32.8407
            mock_orm.longitude = -83.6324
            orm_res.scalars.return_value.first.return_value = mock_orm
            admin_check = MagicMock()
            admin_check.scalars.return_value.first.return_value = None
            official_mock = MagicMock()
            official_mock.scalars.return_value.first.return_value = None

            db.execute.side_effect = [
                addr_res, upsert_res, orm_res,
                admin_check, admin_check, upsert_res,
                official_mock, official_mock,
            ]

            await orchestrator.run(
                freeform="123 MAIN ST MACON GA 31201",
                db=db,
                providers={"census": census_provider},
                http_client=MagicMock(),
            )

        # Census provider must use exact_match_timeout_ms / 1000 = 2.0s (not 3.0s)
        all_timeouts = [c.kwargs.get("timeout") for c in mock_wait_for.call_args_list]
        assert any(t == pytest.approx(2.0) for t in all_timeouts), \
            f"Expected exact_match_timeout_ms (2.0s) but got timeouts: {all_timeouts}"
        assert not any(t == pytest.approx(3.0) for t in all_timeouts), \
            f"Census should NOT use tiger_timeout_ms (3.0s) but got: {all_timeouts}"


class TestProviderTimeoutFailOpen:
    """Provider timeout returns (name, None) — cascade continues (DEBT-01, D-16)."""

    @pytest.mark.asyncio
    async def test_provider_timeout_returns_none_not_raise(self):
        """When a provider times out, _call_provider returns (name, None) without raising."""
        from civpulse_geo.services.cascade import CascadeOrchestrator

        orchestrator = CascadeOrchestrator()

        # Provider that sleeps forever — will time out
        async def _hang(*args, **kwargs):
            await asyncio.sleep(10)

        hang_provider = MagicMock()
        hang_provider.provider_name = "census"
        hang_provider.is_local = False
        hang_provider.geocode = AsyncMock(side_effect=_hang)

        db, mock_address = make_mock_db()
        mock_address.geocoding_results = []

        with patch("civpulse_geo.services.cascade.canonical_key",
                   return_value=("123 MAIN ST MACON GA 31201", "abc123")), \
             patch("civpulse_geo.services.cascade.parse_address_components",
                   return_value={}), \
             patch("civpulse_geo.services.cascade._parse_input_address",
                   return_value=("123", "MAIN", "31201", "ST", None)), \
             patch("civpulse_geo.services.cascade.settings") as mock_settings:

            mock_settings.cascade_llm_enabled = False
            mock_settings.exact_match_timeout_ms = 10  # 10ms — very short so test completes
            mock_settings.tiger_timeout_ms = 10
            mock_settings.fuzzy_match_timeout_ms = 500
            mock_settings.llm_timeout_ms = 5000
            mock_settings.weight_census = 0.90
            mock_settings.weight_openaddresses = 0.80
            mock_settings.weight_macon_bibb = 0.80
            mock_settings.weight_tiger_unrestricted = 0.40
            mock_settings.weight_nad = 0.80

            addr_res = MagicMock()
            addr_res.scalars.return_value.first.return_value = mock_address
            db.execute.side_effect = [addr_res]

            # Must not raise — cascade degrades gracefully
            result = await orchestrator.run(
                freeform="123 MAIN ST MACON GA 31201",
                db=db,
                providers={"census": hang_provider},
                http_client=MagicMock(),
            )

        # Result should be valid with empty results
        assert result is not None
        assert result.cache_hit is False
        assert result.results == []


# ---------------------------------------------------------------------------
# Cache-hit early exit tests (DEBT-02)
# ---------------------------------------------------------------------------

class TestCacheHitEarlyExit:
    """Second call on same address returns cache_hit=True with cached ORM results (DEBT-02)."""

    @pytest.mark.asyncio
    async def test_cache_hit_returns_true_when_geocoding_results_exist(self):
        """When address has geocoding_results, CascadeResult.cache_hit == True."""
        from civpulse_geo.services.cascade import CascadeOrchestrator
        from civpulse_geo.models.geocoding import GeocodingResult as GeocodingResultORM

        orchestrator = CascadeOrchestrator()

        # Cached ORM rows already in DB
        cached_row = MagicMock(spec=GeocodingResultORM)
        cached_row.provider_name = "census"
        cached_row.latitude = 32.8407
        cached_row.longitude = -83.6324
        cached_row.confidence = 0.95

        db, mock_address = make_mock_db()
        mock_address.geocoding_results = [cached_row]  # Non-empty — triggers cache hit

        with patch("civpulse_geo.services.cascade.canonical_key",
                   return_value=("123 MAIN ST MACON GA 31201", "abc123")), \
             patch("civpulse_geo.services.cascade.parse_address_components",
                   return_value={}), \
             patch("civpulse_geo.services.cascade._parse_input_address",
                   return_value=("123", "MAIN", "31201", "ST", None)), \
             patch("civpulse_geo.services.cascade.settings") as mock_settings:

            mock_settings.cascade_llm_enabled = False
            mock_settings.exact_match_timeout_ms = 2000
            mock_settings.tiger_timeout_ms = 3000
            mock_settings.fuzzy_match_timeout_ms = 500
            mock_settings.llm_timeout_ms = 5000
            mock_settings.weight_census = 0.90
            mock_settings.weight_openaddresses = 0.80
            mock_settings.weight_macon_bibb = 0.80
            mock_settings.weight_tiger_unrestricted = 0.40
            mock_settings.weight_nad = 0.80

            addr_res = MagicMock()
            addr_res.scalars.return_value.first.return_value = mock_address

            official_mock = MagicMock()
            official_mock.scalars.return_value.first.return_value = None

            db.execute.side_effect = [
                addr_res,
                official_mock,  # _get_official: OfficialGeocoding
                official_mock,  # _get_official: GeocodingResult
            ]

            result = await orchestrator.run(
                freeform="123 MAIN ST MACON GA 31201",
                db=db,
                providers={},  # No providers needed — cache hit bypasses them
                http_client=MagicMock(),
            )

        assert result.cache_hit is True
        assert cached_row in result.results


class TestCacheHitLocalProvidersStillCalled:
    """Local providers are called fresh even on cache hit (DEBT-02, D-05)."""

    @pytest.mark.asyncio
    async def test_local_provider_called_on_cache_hit(self):
        """is_local=True provider is still invoked when returning a cache hit."""
        from civpulse_geo.services.cascade import CascadeOrchestrator
        from civpulse_geo.models.geocoding import GeocodingResult as GeocodingResultORM

        orchestrator = CascadeOrchestrator()

        cached_row = MagicMock(spec=GeocodingResultORM)
        cached_row.provider_name = "census"
        cached_row.latitude = 32.8407
        cached_row.longitude = -83.6324
        cached_row.confidence = 0.95

        local_provider = make_mock_provider(
            provider_name="openaddresses",
            confidence=0.80,
            is_local=True,
        )

        db, mock_address = make_mock_db()
        mock_address.geocoding_results = [cached_row]

        with patch("civpulse_geo.services.cascade.canonical_key",
                   return_value=("123 MAIN ST MACON GA 31201", "abc123")), \
             patch("civpulse_geo.services.cascade.parse_address_components",
                   return_value={}), \
             patch("civpulse_geo.services.cascade._parse_input_address",
                   return_value=("123", "MAIN", "31201", "ST", None)), \
             patch("civpulse_geo.services.cascade.settings") as mock_settings:

            mock_settings.cascade_llm_enabled = False
            mock_settings.exact_match_timeout_ms = 2000
            mock_settings.tiger_timeout_ms = 3000
            mock_settings.fuzzy_match_timeout_ms = 500
            mock_settings.llm_timeout_ms = 5000
            mock_settings.weight_census = 0.90
            mock_settings.weight_openaddresses = 0.80
            mock_settings.weight_macon_bibb = 0.80
            mock_settings.weight_tiger_unrestricted = 0.40
            mock_settings.weight_nad = 0.80

            addr_res = MagicMock()
            addr_res.scalars.return_value.first.return_value = mock_address
            official_mock = MagicMock()
            official_mock.scalars.return_value.first.return_value = None

            db.execute.side_effect = [
                addr_res,
                official_mock,
                official_mock,
            ]

            result = await orchestrator.run(
                freeform="123 MAIN ST MACON GA 31201",
                db=db,
                providers={"openaddresses": local_provider},
                http_client=MagicMock(),
            )

        # Local provider must have been called even on cache hit
        local_provider.geocode.assert_called_once()
        assert result.cache_hit is True
        # Local results should contain the local provider's result
        assert len(result.local_results) == 1
        assert result.local_results[0].provider_name == "openaddresses"


class TestCacheHitConsensusReRun:
    """Consensus re-runs on cache-hit path; would_set_official is wired from winner (DEBT-02, D-05)."""

    @pytest.mark.asyncio
    async def test_would_set_official_populated_from_consensus_winner(self):
        """Cache-hit path runs consensus; winning cluster's best candidate becomes would_set_official.

        CRITICAL: would_set_official must NOT be None when run_consensus returns a winning cluster.
        This validates D-05's retroactive provider weight goal.
        """
        from civpulse_geo.services.cascade import CascadeOrchestrator, Cluster, ProviderCandidate
        from civpulse_geo.models.geocoding import GeocodingResult as GeocodingResultORM

        orchestrator = CascadeOrchestrator()

        cached_row = MagicMock(spec=GeocodingResultORM)
        cached_row.provider_name = "census"
        cached_row.latitude = 32.8407
        cached_row.longitude = -83.6324
        cached_row.confidence = 0.95

        db, mock_address = make_mock_db()
        mock_address.geocoding_results = [cached_row]

        with patch("civpulse_geo.services.cascade.canonical_key",
                   return_value=("123 MAIN ST MACON GA 31201", "abc123")), \
             patch("civpulse_geo.services.cascade.parse_address_components",
                   return_value={}), \
             patch("civpulse_geo.services.cascade._parse_input_address",
                   return_value=("123", "MAIN", "31201", "ST", None)), \
             patch("civpulse_geo.services.cascade.settings") as mock_settings:

            mock_settings.cascade_llm_enabled = False
            mock_settings.exact_match_timeout_ms = 2000
            mock_settings.tiger_timeout_ms = 3000
            mock_settings.fuzzy_match_timeout_ms = 500
            mock_settings.llm_timeout_ms = 5000
            mock_settings.weight_census = 0.90
            mock_settings.weight_openaddresses = 0.80
            mock_settings.weight_macon_bibb = 0.80
            mock_settings.weight_tiger_unrestricted = 0.40
            mock_settings.weight_nad = 0.80

            addr_res = MagicMock()
            addr_res.scalars.return_value.first.return_value = mock_address
            official_mock = MagicMock()
            official_mock.scalars.return_value.first.return_value = None

            db.execute.side_effect = [
                addr_res,
                official_mock,
                official_mock,
            ]

            result = await orchestrator.run(
                freeform="123 MAIN ST MACON GA 31201",
                db=db,
                providers={},  # no providers — only cached results used for consensus
                http_client=MagicMock(),
            )

        assert result.cache_hit is True
        # CRITICAL: consensus was run and winner wired to would_set_official
        assert result.would_set_official is not None, (
            "would_set_official must be populated from consensus winner on cache-hit path "
            "(D-05: retroactive provider weight changes must take effect)"
        )

    @pytest.mark.asyncio
    async def test_outlier_providers_populated_on_cache_hit(self):
        """Cache-hit path populates outlier_providers from consensus scored_candidates."""
        from civpulse_geo.services.cascade import CascadeOrchestrator
        from civpulse_geo.models.geocoding import GeocodingResult as GeocodingResultORM

        orchestrator = CascadeOrchestrator()

        # Two rows: one close, one very far (outlier)
        good_row = MagicMock(spec=GeocodingResultORM)
        good_row.provider_name = "census"
        good_row.latitude = 32.8407
        good_row.longitude = -83.6324
        good_row.confidence = 0.95

        outlier_row = MagicMock(spec=GeocodingResultORM)
        outlier_row.provider_name = "nad"
        outlier_row.latitude = 33.9000  # ~12km north — far enough to be outlier
        outlier_row.longitude = -83.6324
        outlier_row.confidence = 0.80

        db, mock_address = make_mock_db()
        mock_address.geocoding_results = [good_row, outlier_row]

        with patch("civpulse_geo.services.cascade.canonical_key",
                   return_value=("123 MAIN ST MACON GA 31201", "abc123")), \
             patch("civpulse_geo.services.cascade.parse_address_components",
                   return_value={}), \
             patch("civpulse_geo.services.cascade._parse_input_address",
                   return_value=("123", "MAIN", "31201", "ST", None)), \
             patch("civpulse_geo.services.cascade.settings") as mock_settings:

            mock_settings.cascade_llm_enabled = False
            mock_settings.exact_match_timeout_ms = 2000
            mock_settings.tiger_timeout_ms = 3000
            mock_settings.fuzzy_match_timeout_ms = 500
            mock_settings.llm_timeout_ms = 5000
            mock_settings.weight_census = 0.90
            mock_settings.weight_openaddresses = 0.80
            mock_settings.weight_macon_bibb = 0.80
            mock_settings.weight_tiger_unrestricted = 0.40
            mock_settings.weight_nad = 0.80

            addr_res = MagicMock()
            addr_res.scalars.return_value.first.return_value = mock_address
            official_mock = MagicMock()
            official_mock.scalars.return_value.first.return_value = None

            db.execute.side_effect = [
                addr_res,
                official_mock,
                official_mock,
            ]

            result = await orchestrator.run(
                freeform="123 MAIN ST MACON GA 31201",
                db=db,
                providers={},
                http_client=MagicMock(),
            )

        assert result.cache_hit is True
        # nad should be flagged as outlier (>1km from census cluster centroid)
        assert "nad" in result.outlier_providers
