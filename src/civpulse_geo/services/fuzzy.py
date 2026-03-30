"""FuzzyMatcher service: pg_trgm word_similarity() + dmetaphone() tiebreaker.

Implements the fuzzy street name matching component for Phase 13. Called by
the Phase 14 orchestrator after all exact-match providers return NO_MATCH.

Architecture (D-05):
  - New service class at services/fuzzy.py
  - Queries ALL local provider staging tables (D-06): OA, NAD, Macon-Bibb
  - word_similarity() threshold 0.65 (D-13)
  - dmetaphone() tiebreaker when top candidates are within 0.05 (D-12)
  - Confidence maps to 0.50-0.75 range (D-07) — slots between scourgify (0.3)
    and exact local matches (0.8+) for Phase 14 consensus scoring
  - Returns single best match only (D-14)

word_similarity() argument order:
  word_similarity(needle, haystack) — input first, stored second (Research Pitfall 1)
"""
from __future__ import annotations

from dataclasses import dataclass

from geoalchemy2.types import Geometry
from loguru import logger
from sqlalchemy import func, literal, select, text, union_all
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from civpulse_geo.models.macon_bibb import MaconBibbPoint
from civpulse_geo.models.nad import NADPoint
from civpulse_geo.models.openaddresses import OpenAddressesPoint

# ---------------------------------------------------------------------------
# Constants (D-07, D-12, D-13)
# ---------------------------------------------------------------------------

FUZZY_SIMILARITY_THRESHOLD = 0.65  # D-13: minimum word_similarity score
FUZZY_TIEBREAK_GAP = 0.05          # D-12: gap threshold for dmetaphone tiebreak
FUZZY_CONFIDENCE_MIN = 0.50        # D-07: confidence at similarity=0.65
FUZZY_CONFIDENCE_MAX = 0.75        # D-07: confidence at similarity=1.0


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class FuzzyMatchResult:
    """Single best fuzzy match result returned by FuzzyMatcher.find_fuzzy_match()."""

    street_name: str        # corrected street name from staging table
    score: float            # word_similarity score (0.65-1.0)
    source: str             # "openaddresses" | "nad" | "macon_bibb"
    confidence: float       # mapped confidence (0.50-0.75)
    street_number: str | None
    city: str | None
    zip_code: str | None
    lat: float | None
    lng: float | None


# ---------------------------------------------------------------------------
# Helper: similarity → confidence mapping
# ---------------------------------------------------------------------------

def similarity_to_confidence(similarity: float) -> float:
    """Map word_similarity 0.65-1.0 to confidence 0.50-0.75 (D-07).

    Linear interpolation:
        confidence = 0.50 + (similarity - 0.65) / 0.35 * 0.25
    """
    normalized = (similarity - FUZZY_SIMILARITY_THRESHOLD) / (1.0 - FUZZY_SIMILARITY_THRESHOLD)
    return FUZZY_CONFIDENCE_MIN + normalized * (FUZZY_CONFIDENCE_MAX - FUZZY_CONFIDENCE_MIN)


# ---------------------------------------------------------------------------
# FuzzyMatcher service
# ---------------------------------------------------------------------------

class FuzzyMatcher:
    """Fuzzy street name matcher using pg_trgm word_similarity() + dmetaphone().

    Queries OA, NAD, and Macon-Bibb staging tables (D-06) and returns the
    single best candidate above FUZZY_SIMILARITY_THRESHOLD (D-14).
    Uses dmetaphone() tiebreaker when multiple candidates score within
    FUZZY_TIEBREAK_GAP of each other (D-12).
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def find_fuzzy_match(
        self,
        street_name: str,
        zip_code: str | None = None,
        street_number: str | None = None,
    ) -> FuzzyMatchResult | None:
        """Find best fuzzy match across OA, NAD, Macon-Bibb staging tables.

        Returns the single best candidate (D-14) above FUZZY_SIMILARITY_THRESHOLD,
        or None if nothing qualifies.

        Uses word_similarity(needle, haystack) — input first, stored second
        (Research Pitfall 1).

        When the top candidate leads by > FUZZY_TIEBREAK_GAP over the runner-up,
        it wins immediately. When multiple candidates score within the gap,
        dmetaphone() selects the phonetically closest (D-12).

        Args:
            street_name: Street name from the degraded input address.
            zip_code: Optional ZIP code for filtering (LIKE prefix match).
            street_number: Optional house number (reserved for future narrowing).

        Returns:
            FuzzyMatchResult or None.
        """
        candidates = await self._query_candidates(street_name, zip_code)

        if not candidates:
            return None

        # Sort descending by score (already filtered above threshold)
        candidates.sort(key=lambda r: r.score, reverse=True)

        top = candidates[0]

        if len(candidates) == 1:
            # Single candidate — return immediately
            return self._to_result(top)

        second = candidates[1]

        if (top.score - second.score) > FUZZY_TIEBREAK_GAP:
            # Clear winner — no tiebreak needed
            return self._to_result(top)

        # Ambiguous — use dmetaphone tiebreaker (D-12)
        logger.debug(
            "FuzzyMatcher: dmetaphone tiebreak for input={!r} (top={} score={:.3f}, "
            "runner-up={} score={:.3f})",
            street_name,
            top.street_name,
            top.score,
            second.street_name,
            second.score,
        )
        best = await self._dmetaphone_tiebreak(street_name, candidates)
        return self._to_result(best)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _query_candidates(
        self,
        street_name: str,
        zip_code: str | None,
    ) -> list:
        """Execute UNION ALL query across all three staging tables.

        Returns rows above FUZZY_SIMILARITY_THRESHOLD ordered by score DESC, LIMIT 5.
        Each row has: street_name, street_number, city, zip_code, lat, lng, score, source.
        """
        input_upper = street_name.upper()

        # --- OpenAddresses sub-query ---
        oa_q = (
            select(
                OpenAddressesPoint.street_name,
                OpenAddressesPoint.street_number,
                OpenAddressesPoint.city,
                OpenAddressesPoint.postcode.label("zip_code"),
                func.ST_Y(OpenAddressesPoint.location.cast(Geometry)).label("lat"),
                func.ST_X(OpenAddressesPoint.location.cast(Geometry)).label("lng"),
                func.word_similarity(input_upper, OpenAddressesPoint.street_name).label("score"),
                literal("openaddresses").label("source"),
            )
            .where(
                func.word_similarity(input_upper, OpenAddressesPoint.street_name)
                >= FUZZY_SIMILARITY_THRESHOLD
            )
        )
        if zip_code:
            prefix = zip_code[:5]
            oa_q = oa_q.where(OpenAddressesPoint.postcode.like(f"{prefix}%"))

        # --- NAD sub-query ---
        nad_q = (
            select(
                NADPoint.street_name,
                NADPoint.street_number,
                NADPoint.city,
                NADPoint.zip_code,
                func.ST_Y(NADPoint.location.cast(Geometry)).label("lat"),
                func.ST_X(NADPoint.location.cast(Geometry)).label("lng"),
                func.word_similarity(input_upper, NADPoint.street_name).label("score"),
                literal("nad").label("source"),
            )
            .where(
                func.word_similarity(input_upper, NADPoint.street_name)
                >= FUZZY_SIMILARITY_THRESHOLD
            )
        )
        if zip_code:
            prefix = zip_code[:5]
            nad_q = nad_q.where(NADPoint.zip_code.like(f"{prefix}%"))

        # --- Macon-Bibb sub-query ---
        mb_q = (
            select(
                MaconBibbPoint.street_name,
                MaconBibbPoint.street_number,
                MaconBibbPoint.city,
                MaconBibbPoint.zip_code,
                func.ST_Y(MaconBibbPoint.location.cast(Geometry)).label("lat"),
                func.ST_X(MaconBibbPoint.location.cast(Geometry)).label("lng"),
                func.word_similarity(input_upper, MaconBibbPoint.street_name).label("score"),
                literal("macon_bibb").label("source"),
            )
            .where(
                func.word_similarity(input_upper, MaconBibbPoint.street_name)
                >= FUZZY_SIMILARITY_THRESHOLD
            )
        )
        if zip_code:
            prefix = zip_code[:5]
            mb_q = mb_q.where(MaconBibbPoint.zip_code.like(f"{prefix}%"))

        # UNION ALL, ORDER BY score DESC, LIMIT 5
        union_stmt = (
            union_all(oa_q, nad_q, mb_q)
            .order_by(text("score DESC"))
            .limit(5)
        )

        async with self._session_factory() as session:
            db_result = await session.execute(union_stmt)
            rows = db_result.mappings().all()

        return [_CandidateRow(r) for r in rows]

    async def _dmetaphone_tiebreak(self, input_street: str, candidates: list) -> object:
        """Select the phonetically closest candidate using PostgreSQL dmetaphone().

        Executes a SQL query that computes dmetaphone() for each candidate
        street_name and compares against the input street name's dmetaphone code.
        This keeps phonetic computation in the DB (fuzzystrmatch extension,
        already installed as Tiger dependency).

        Returns the candidate with the best phonetic match. If no phonetic match
        is found, returns the highest-scoring candidate.
        """
        input_upper = input_street.upper()

        # Use raw SQL with unnest to compute dmetaphone for each candidate
        # and compare against the input
        placeholders = ", ".join(
            f"(:name_{i}, :score_{i}, :source_{i})"
            for i in range(len(candidates))
        )
        params: dict = {}
        for i, c in enumerate(candidates):
            params[f"name_{i}"] = c.street_name
            params[f"score_{i}"] = c.score
            params[f"source_{i}"] = c.source
        params["input"] = input_upper

        sql = text(f"""
            WITH cands(street_name, score, source) AS (
                VALUES {placeholders}
            )
            SELECT
                street_name,
                score,
                source,
                dmetaphone(upper(street_name)) = dmetaphone(:input) AS primary_match,
                dmetaphone_alt(upper(street_name)) = dmetaphone(:input) AS alt_match
            FROM cands
            ORDER BY
                (dmetaphone(upper(street_name)) = dmetaphone(:input)) DESC,
                (dmetaphone_alt(upper(street_name)) = dmetaphone(:input)) DESC,
                score DESC
            LIMIT 1
        """)

        async with self._session_factory() as session:
            try:
                result = await session.execute(sql, params)
                row = result.mappings().first()
                if row:
                    # Find the matching candidate from original list
                    for c in candidates:
                        if c.street_name == row["street_name"] and c.source == row["source"]:
                            return c
            except Exception as exc:
                logger.warning(
                    "FuzzyMatcher: dmetaphone tiebreak SQL failed ({}); falling back to score",
                    exc,
                )

        # Fallback: highest-score candidate
        return candidates[0]

    @staticmethod
    def _to_result(candidate) -> FuzzyMatchResult:
        """Convert a _CandidateRow to a FuzzyMatchResult with confidence mapping."""
        confidence = similarity_to_confidence(float(candidate.score))
        return FuzzyMatchResult(
            street_name=candidate.street_name,
            score=float(candidate.score),
            source=candidate.source,
            confidence=confidence,
            street_number=candidate.street_number,
            city=candidate.city,
            zip_code=candidate.zip_code,
            lat=float(candidate.lat) if candidate.lat is not None else None,
            lng=float(candidate.lng) if candidate.lng is not None else None,
        )


# ---------------------------------------------------------------------------
# Internal helper class
# ---------------------------------------------------------------------------

class _CandidateRow:
    """Thin wrapper around a SQLAlchemy Mapping row for attribute-style access."""

    __slots__ = ("street_name", "street_number", "city", "zip_code", "lat", "lng", "score", "source")

    def __init__(self, mapping) -> None:
        self.street_name = mapping["street_name"]
        self.street_number = mapping.get("street_number")
        self.city = mapping.get("city")
        self.zip_code = mapping.get("zip_code")
        self.lat = mapping.get("lat")
        self.lng = mapping.get("lng")
        self.score = mapping["score"]
        self.source = mapping["source"]
