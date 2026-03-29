"""Unit tests for FuzzyMatcher service.

TDD RED phase: Tests written first. Uses mock async sessions returning
controlled rows to validate FuzzyMatcher behavior without a real DB.

Covers:
  - find_fuzzy_match() returns FuzzyMatchResult above threshold
  - find_fuzzy_match() returns None below threshold
  - dmetaphone() tiebreaker when candidates within 0.05 gap (D-12)
  - No tiebreak needed when top candidate leads by > 0.05
  - similarity_to_confidence() boundary mapping (D-07)
  - Queries all three staging tables (D-06)
  - Returns best single match only (D-14)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------

def _make_row(street_name, street_number, city, zip_code, lat, lng, score, source):
    """Build a mock row that looks like a SQLAlchemy Row result."""
    row = MagicMock()
    row.street_name = street_name
    row.street_number = street_number
    row.city = city
    row.zip_code = zip_code
    row.lat = lat
    row.lng = lng
    row.score = score
    row.source = source
    return row


def _make_session_factory(rows):
    """Return an async_sessionmaker mock whose sessions return `rows` from execute()."""
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = rows

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    mock_factory = MagicMock()
    mock_factory.return_value = mock_session
    return mock_factory, mock_session


# ---------------------------------------------------------------------------
# similarity_to_confidence() tests
# ---------------------------------------------------------------------------

class TestSimilarityToConfidence:
    """Test linear mapping from word_similarity to confidence (D-07)."""

    def test_boundary_low(self):
        """similarity=0.65 → confidence=0.50 (D-07 lower bound)."""
        from civpulse_geo.services.fuzzy import similarity_to_confidence
        result = similarity_to_confidence(0.65)
        assert abs(result - 0.50) < 1e-9

    def test_boundary_high(self):
        """similarity=1.0 → confidence=0.75 (D-07 upper bound)."""
        from civpulse_geo.services.fuzzy import similarity_to_confidence
        result = similarity_to_confidence(1.0)
        assert abs(result - 0.75) < 1e-9

    def test_midpoint(self):
        """similarity=0.80 → approximately 0.607 (linear interpolation)."""
        from civpulse_geo.services.fuzzy import similarity_to_confidence
        # 0.50 + (0.80 - 0.65) / 0.35 * 0.25 = 0.50 + 0.15/0.35 * 0.25 ≈ 0.607
        result = similarity_to_confidence(0.80)
        expected = 0.50 + (0.80 - 0.65) / 0.35 * 0.25
        assert abs(result - expected) < 1e-6

    def test_exact_threshold(self):
        """similarity=FUZZY_SIMILARITY_THRESHOLD → FUZZY_CONFIDENCE_MIN."""
        from civpulse_geo.services.fuzzy import (
            similarity_to_confidence,
            FUZZY_SIMILARITY_THRESHOLD,
            FUZZY_CONFIDENCE_MIN,
        )
        result = similarity_to_confidence(FUZZY_SIMILARITY_THRESHOLD)
        assert abs(result - FUZZY_CONFIDENCE_MIN) < 1e-9


# ---------------------------------------------------------------------------
# FuzzyMatcher.find_fuzzy_match() — basic tests
# ---------------------------------------------------------------------------

class TestFindFuzzyMatchBasic:
    """Tests for basic FuzzyMatcher.find_fuzzy_match() behavior."""

    @pytest.mark.asyncio
    async def test_returns_result_above_threshold(self):
        """Returns FuzzyMatchResult when best candidate is above 0.65 threshold."""
        from civpulse_geo.services.fuzzy import FuzzyMatcher, FuzzyMatchResult

        row = _make_row("MERCER", "100", "MACON", "31201", 32.84, -83.63, 0.80, "openaddresses")
        factory, session = _make_session_factory([row])

        matcher = FuzzyMatcher(factory)
        result = await matcher.find_fuzzy_match("MRCCER", zip_code="31201")

        assert result is not None
        assert isinstance(result, FuzzyMatchResult)
        assert result.street_name == "MERCER"
        assert result.source == "openaddresses"
        assert result.score == 0.80
        assert 0.50 <= result.confidence <= 0.75

    @pytest.mark.asyncio
    async def test_returns_none_below_threshold(self):
        """Returns None when no candidate meets 0.65 threshold (empty result set)."""
        from civpulse_geo.services.fuzzy import FuzzyMatcher

        factory, session = _make_session_factory([])

        matcher = FuzzyMatcher(factory)
        result = await matcher.find_fuzzy_match("XYZQWK", zip_code="31201")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_best_single_match_only(self):
        """Returns only the single best match (D-14), not a list."""
        from civpulse_geo.services.fuzzy import FuzzyMatcher, FuzzyMatchResult

        rows = [
            _make_row("MERCER", "100", "MACON", "31201", 32.84, -83.63, 0.80, "openaddresses"),
            _make_row("MILLER", "200", "MACON", "31201", 32.85, -83.64, 0.70, "nad"),
        ]
        factory, session = _make_session_factory(rows)

        matcher = FuzzyMatcher(factory)
        result = await matcher.find_fuzzy_match("MRCCER", zip_code="31201")

        # Must return a single FuzzyMatchResult, not a list
        assert isinstance(result, FuzzyMatchResult)
        assert result.street_name == "MERCER"
        assert result.score == 0.80

    @pytest.mark.asyncio
    async def test_confidence_in_valid_range(self):
        """All returned confidence values must be in [0.50, 0.75]."""
        from civpulse_geo.services.fuzzy import FuzzyMatcher

        for score in [0.65, 0.75, 0.85, 0.95, 1.0]:
            row = _make_row("MERCER", "100", "MACON", "31201", 32.84, -83.63, score, "openaddresses")
            factory, session = _make_session_factory([row])
            matcher = FuzzyMatcher(factory)
            result = await matcher.find_fuzzy_match("MRCCER")
            assert result is not None
            assert 0.50 <= result.confidence <= 0.75, (
                f"confidence {result.confidence} out of range for score={score}"
            )


# ---------------------------------------------------------------------------
# FuzzyMatcher.find_fuzzy_match() — tiebreaker tests (D-12)
# ---------------------------------------------------------------------------

class TestFindFuzzyMatchTiebreaker:
    """Tests for dmetaphone() tiebreaker logic (D-12)."""

    @pytest.mark.asyncio
    async def test_no_tiebreak_when_clear_winner(self):
        """When top candidate leads by > 0.05, it wins without dmetaphone."""
        from civpulse_geo.services.fuzzy import FuzzyMatcher

        rows = [
            _make_row("MERCER", "100", "MACON", "31201", 32.84, -83.63, 0.80, "openaddresses"),
            _make_row("MILLER", "200", "MACON", "31201", 32.85, -83.64, 0.70, "nad"),
        ]
        factory, session = _make_session_factory(rows)

        matcher = FuzzyMatcher(factory)
        result = await matcher.find_fuzzy_match("MRCCER", zip_code="31201")

        # MERCER leads by 0.10 > 0.05 gap — wins without tiebreak
        assert result is not None
        assert result.street_name == "MERCER"

    @pytest.mark.asyncio
    async def test_dmetaphone_tiebreak_picks_phonetic_match(self):
        """When candidates within 0.05, dmetaphone picks phonetically closest (D-12).

        Input "FORSITH" is phonetically close to "FORSYTH" (FRSX) rather than
        "FORSYTT" (FRST). Both candidates are within 0.05 of each other.
        """
        from civpulse_geo.services.fuzzy import FuzzyMatcher

        rows = [
            _make_row("FORSYTH", "100", "MACON", "31201", 32.84, -83.63, 0.80, "openaddresses"),
            _make_row("FORSYTT", "200", "MACON", "31201", 32.85, -83.64, 0.78, "nad"),
        ]
        factory, session = _make_session_factory(rows)

        matcher = FuzzyMatcher(factory)
        result = await matcher.find_fuzzy_match("FORSITH", zip_code="31201")

        # FORSYTH should win — phonetically closer to FORSITH
        assert result is not None
        assert result.street_name == "FORSYTH"

    @pytest.mark.asyncio
    async def test_single_candidate_wins_without_tiebreak(self):
        """Single candidate above threshold wins immediately (no tiebreak needed)."""
        from civpulse_geo.services.fuzzy import FuzzyMatcher

        row = _make_row("POPLAR", "100", "MACON", "31201", 32.84, -83.63, 0.95, "openaddresses")
        factory, session = _make_session_factory([row])

        matcher = FuzzyMatcher(factory)
        result = await matcher.find_fuzzy_match("POPLR", zip_code="31201")

        assert result is not None
        assert result.street_name == "POPLAR"


# ---------------------------------------------------------------------------
# FuzzyMatcher — all three staging tables tested (D-06)
# ---------------------------------------------------------------------------

class TestFindFuzzyMatchAllTables:
    """Verifies FuzzyMatcher queries all three staging tables (D-06)."""

    @pytest.mark.asyncio
    async def test_queries_all_three_tables(self):
        """FuzzyMatcher executes a UNION ALL across OA, NAD, and Macon-Bibb tables.

        We check that the rendered SQL includes all three table names in the
        query sent to the session.
        """
        from civpulse_geo.services.fuzzy import FuzzyMatcher

        captured_queries = []

        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = []

        mock_session = AsyncMock()

        async def capture_execute(stmt, *args, **kwargs):
            try:
                from sqlalchemy.dialects import postgresql
                compiled = stmt.compile(dialect=postgresql.dialect())
                captured_queries.append(str(compiled))
            except Exception:
                captured_queries.append(repr(stmt))
            return mock_result

        mock_session.execute = capture_execute
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_factory = MagicMock()
        mock_factory.return_value = mock_session

        matcher = FuzzyMatcher(mock_factory)
        await matcher.find_fuzzy_match("MRCCER", zip_code="31201")

        assert len(captured_queries) >= 1
        combined_sql = " ".join(captured_queries).lower()
        assert "openaddresses_points" in combined_sql
        assert "nad_points" in combined_sql
        assert "macon_bibb_points" in combined_sql

    @pytest.mark.asyncio
    async def test_returns_nad_source(self):
        """FuzzyMatcher can return a result sourced from nad (source='nad')."""
        from civpulse_geo.services.fuzzy import FuzzyMatcher

        row = _make_row("WALNUT", "500", "MACON", "31201", 32.85, -83.65, 0.90, "nad")
        factory, session = _make_session_factory([row])

        matcher = FuzzyMatcher(factory)
        result = await matcher.find_fuzzy_match("WALNIT", zip_code="31201")

        assert result is not None
        assert result.street_name == "WALNUT"
        assert result.source == "nad"

    @pytest.mark.asyncio
    async def test_returns_macon_bibb_source(self):
        """FuzzyMatcher can return a result sourced from macon_bibb."""
        from civpulse_geo.services.fuzzy import FuzzyMatcher

        row = _make_row("VINEVILLE", "300", "MACON", "31204", 32.87, -83.66, 0.85, "macon_bibb")
        factory, session = _make_session_factory([row])

        matcher = FuzzyMatcher(factory)
        result = await matcher.find_fuzzy_match("VINVELLE", zip_code="31204")

        assert result is not None
        assert result.street_name == "VINEVILLE"
        assert result.source == "macon_bibb"
