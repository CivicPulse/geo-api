"""CascadeOrchestrator: staged resolution pipeline with consensus scoring.

Implements the Phase 14 cascade:
    normalize → spell-correct → exact match → fuzzy → consensus → auto-set official

Key design decisions (from 14-CONTEXT.md):
- D-05: All providers (local + remote) called in parallel in exact-match stage
- D-06: Greedy single-pass clustering sorted by weight descending
- D-07: Weighted centroid: centroid = sum(w*coord) / sum(w)
- D-08: Provider trust weights from settings (Census=0.90, OA=0.80, etc.)
- D-09: Fuzzy effective weight = provider_weight * (fuzzy_confidence / 0.80)
- D-10: Winning cluster = highest total_weight
- D-11: Single result: auto-set only when confidence >= 0.80
- D-12: Early-exit when ANY exact-match result has confidence >= 0.80
- D-13: Consensus scoring always runs (even on early-exit)
- D-16: Stage timeouts degrade gracefully — empty result, cascade continues
- D-22: ON CONFLICT DO UPDATE for OfficialGeocoding; admin_override never overwritten
"""
from __future__ import annotations

import asyncio
import math
import time
from dataclasses import dataclass, field
from typing import Any

import httpx
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from civpulse_geo.config import settings
from civpulse_geo.models.address import Address
from civpulse_geo.models.geocoding import (
    GeocodingResult as GeocodingResultORM,
    OfficialGeocoding,
    AdminOverride,
)
from civpulse_geo.normalization import canonical_key, parse_address_components
from civpulse_geo.providers.base import GeocodingProvider
from civpulse_geo.providers.openaddresses import _parse_input_address
from civpulse_geo.providers.schemas import GeocodingResult as GeocodingResultSchema
from civpulse_geo.services.fuzzy import FuzzyMatcher, FuzzyMatchResult
from civpulse_geo.spell.corrector import SpellCorrector


# ---------------------------------------------------------------------------
# Provider weight mapping (CONS-02, D-08)
# ---------------------------------------------------------------------------

def get_provider_weight(provider_name: str) -> float:
    """Map provider_name to its configured trust weight.

    Uses settings fields for all known providers. Returns 0.50 for unknown
    providers (reasonable mid-point for untrusted sources).
    """
    # Built lazily to always use current settings values
    weight_map = {
        "census": settings.weight_census,
        "openaddresses": settings.weight_openaddresses,
        "macon_bibb": settings.weight_macon_bibb,
        "tiger": settings.weight_tiger_unrestricted,
        "nad": settings.weight_nad,
    }
    return weight_map.get(provider_name, 0.50)


# ---------------------------------------------------------------------------
# Haversine distance (in-Python, avoids DB round-trip for clustering)
# ---------------------------------------------------------------------------

_EARTH_RADIUS_M = 6_371_000.0


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Return the great-circle distance in meters between two WGS84 points.

    Uses the Haversine formula with Earth radius = 6,371,000 m.
    """
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)

    a = (
        math.sin(d_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2.0) ** 2
    )
    c = 2.0 * math.asin(math.sqrt(a))
    return _EARTH_RADIUS_M * c


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ProviderCandidate:
    """Internal normalized representation used across all consensus scoring stages."""

    provider_name: str
    lat: float
    lng: float
    confidence: float
    weight: float               # effective trust weight (may be scaled for fuzzy)
    location_type: str | None = None
    raw_response: dict | None = None
    is_fuzzy: bool = False
    is_outlier: bool = False
    source_result: Any = None   # original GeocodingResultSchema or FuzzyMatchResult
    geocoding_result_id: int | None = None  # set after DB upsert for remote providers


@dataclass
class Cluster:
    """Spatial cluster of ProviderCandidates for consensus scoring (D-06)."""

    members: list[ProviderCandidate] = field(default_factory=list)
    centroid_lat: float = 0.0
    centroid_lng: float = 0.0
    total_weight: float = 0.0

    def add(self, candidate: ProviderCandidate) -> None:
        """Add a candidate, recomputing the weighted centroid (D-07)."""
        self.members.append(candidate)
        self.total_weight += candidate.weight
        # Recompute weighted centroid
        sum_w = sum(m.weight for m in self.members)
        if sum_w > 0:
            self.centroid_lat = sum(m.lat * m.weight for m in self.members) / sum_w
            self.centroid_lng = sum(m.lng * m.weight for m in self.members) / sum_w

    @classmethod
    def from_seed(cls, candidate: ProviderCandidate) -> "Cluster":
        """Create a new cluster with the given candidate as seed."""
        c = cls()
        c.add(candidate)
        return c


@dataclass
class CascadeResult:
    """Result returned from CascadeOrchestrator.run()."""

    address_hash: str
    normalized_address: str
    address: Address
    cache_hit: bool
    results: list[GeocodingResultORM]           # remote ORM rows
    local_results: list[GeocodingResultSchema]  # local provider schema results
    official: GeocodingResultORM | None = None
    would_set_official: ProviderCandidate | None = None  # dry_run only
    cascade_trace: list[dict] | None = None
    outlier_providers: set[str] = field(default_factory=set)


# ---------------------------------------------------------------------------
# Consensus engine
# ---------------------------------------------------------------------------

def run_consensus(
    candidates: list[ProviderCandidate],
) -> tuple[Cluster | None, list[ProviderCandidate]]:
    """Greedy single-pass spatial clustering with outlier flagging.

    Algorithm (D-06):
    1. Filter candidates to those with valid lat/lng and confidence > 0.0
    2. Sort by weight descending
    3. First candidate seeds cluster 1
    4. Each subsequent candidate joins the nearest cluster if haversine_m <= 100m
       otherwise starts a new cluster
    5. Winning cluster = max by total_weight (D-10)
    6. Flag outliers: candidates > 1km from winning centroid

    Returns:
        (winning_cluster, all_candidates_with_outlier_flags)
        winning_cluster is None if no valid candidates.
    """
    if not candidates:
        return None, []

    # Filter valid candidates (must have lat/lng and positive confidence)
    valid = [c for c in candidates if c.lat is not None and c.lng is not None and c.confidence > 0.0]
    invalid = [c for c in candidates if c not in valid]

    if not valid:
        return None, candidates

    # Sort by weight descending (D-06)
    valid.sort(key=lambda c: c.weight, reverse=True)

    # Greedy single-pass clustering
    clusters: list[Cluster] = []
    for candidate in valid:
        if not clusters:
            clusters.append(Cluster.from_seed(candidate))
            continue

        # Find nearest cluster
        nearest_cluster = None
        nearest_dist = float("inf")
        for cluster in clusters:
            dist = haversine_m(
                candidate.lat, candidate.lng,
                cluster.centroid_lat, cluster.centroid_lng,
            )
            if dist < nearest_dist:
                nearest_dist = dist
                nearest_cluster = cluster

        if nearest_dist <= 100.0 and nearest_cluster is not None:
            nearest_cluster.add(candidate)
        else:
            clusters.append(Cluster.from_seed(candidate))

    # Winning cluster = max total_weight (D-10)
    winning_cluster = max(clusters, key=lambda c: c.total_weight)

    # Outlier flagging: candidates > 1km from winning centroid
    for candidate in valid:
        dist = haversine_m(
            candidate.lat, candidate.lng,
            winning_cluster.centroid_lat, winning_cluster.centroid_lng,
        )
        if dist > 1000.0:
            candidate.is_outlier = True

    all_candidates = valid + invalid
    return winning_cluster, all_candidates


# ---------------------------------------------------------------------------
# CascadeOrchestrator
# ---------------------------------------------------------------------------

class CascadeOrchestrator:
    """Staged cascade resolution pipeline (CASC-01).

    Stages: normalize → spell-correct → exact match → fuzzy → consensus → auto-set

    Designed to be instantiated per-request (stateless like GeocodingService).
    """

    async def run(
        self,
        freeform: str,
        db: AsyncSession,
        providers: dict[str, GeocodingProvider],
        http_client: httpx.AsyncClient,
        spell_corrector: SpellCorrector | None = None,
        fuzzy_matcher: FuzzyMatcher | None = None,
        dry_run: bool = False,
        trace: bool = False,
    ) -> CascadeResult:
        """Execute the full cascade pipeline.

        Args:
            freeform: Raw address string from the caller.
            db: Async database session.
            providers: Dict of provider_name -> GeocodingProvider instance.
            http_client: Shared httpx.AsyncClient.
            spell_corrector: Optional SpellCorrector for stage 1.
            fuzzy_matcher: Optional FuzzyMatcher for stage 3.
            dry_run: If True, run full cascade but don't write OfficialGeocoding.
            trace: If True, populate cascade_trace in result.

        Returns:
            CascadeResult with all pipeline outputs.
        """
        cascade_trace: list[dict] = [] if (trace or dry_run) else []
        t_total_start = time.monotonic()

        # ----------------------------------------------------------------
        # Stage 1: Normalize + spell-correct
        # ----------------------------------------------------------------
        t_stage = time.monotonic()

        if spell_corrector is not None:
            from civpulse_geo.services.geocoding import GeocodingService
            freeform = GeocodingService._apply_spell_correction(freeform, spell_corrector)

        normalized, address_hash = canonical_key(freeform)

        # Find or create Address record
        addr_result = await db.execute(
            select(Address)
            .where(Address.address_hash == address_hash)
        )
        address = addr_result.scalars().first()

        if address is None:
            components = parse_address_components(freeform)
            address = Address(
                original_input=freeform,
                normalized_address=normalized,
                address_hash=address_hash,
                street_number=components.get("street_number"),
                street_name=components.get("street_name"),
                street_suffix=components.get("street_suffix"),
                street_predirection=components.get("street_predirection"),
                street_postdirection=components.get("street_postdirection"),
                unit_type=components.get("unit_type"),
                unit_number=components.get("unit_number"),
                city=components.get("city"),
                state=components.get("state"),
                zip_code=components.get("zip_code"),
            )
            db.add(address)
            await db.flush()  # get address.id

        if trace or dry_run:
            cascade_trace.append({
                "stage": "normalize",
                "input": freeform,
                "output": normalized,
                "address_hash": address_hash,
                "spell_corrected": spell_corrector is not None,
                "ms": round((time.monotonic() - t_stage) * 1000, 1),
            })

        # ----------------------------------------------------------------
        # Stage 2: Exact match — all providers in parallel (D-05)
        # ----------------------------------------------------------------
        t_stage = time.monotonic()

        local_providers = {k: v for k, v in providers.items() if v.is_local}
        remote_providers = {k: v for k, v in providers.items() if not v.is_local}

        candidates: list[ProviderCandidate] = []
        new_results: list[GeocodingResultORM] = []
        local_results: list[GeocodingResultSchema] = []

        # Build tasks for all providers
        async def _call_provider(
            provider_name: str, provider: GeocodingProvider
        ) -> tuple[str, GeocodingResultSchema | None]:
            try:
                result = await asyncio.wait_for(
                    provider.geocode(normalized, http_client=http_client),
                    timeout=settings.exact_match_timeout_ms / 1000,
                )
                return provider_name, result
            except asyncio.TimeoutError:
                logger.warning(
                    "CascadeOrchestrator: provider {} timed out after {}ms",
                    provider_name, settings.exact_match_timeout_ms,
                )
                return provider_name, None
            except Exception as exc:
                logger.warning(
                    "CascadeOrchestrator: provider {} raised {}: {}",
                    provider_name, type(exc).__name__, exc,
                )
                return provider_name, None

        # Gather all provider calls in parallel
        all_provider_items = list(providers.items())
        if all_provider_items:
            tasks = [_call_provider(name, prov) for name, prov in all_provider_items]
            provider_results = await asyncio.gather(*tasks, return_exceptions=True)
        else:
            provider_results = []

        # Process results
        for item in provider_results:
            if isinstance(item, Exception):
                logger.warning("CascadeOrchestrator: provider task raised exception: {}", item)
                continue

            provider_name, schema_result = item
            if schema_result is None:
                continue

            provider = providers[provider_name]

            if provider.is_local:
                local_results.append(schema_result)
                # Add to candidates for consensus (no DB write)
                if schema_result.confidence > 0.0:
                    candidates.append(ProviderCandidate(
                        provider_name=provider_name,
                        lat=schema_result.lat,
                        lng=schema_result.lng,
                        confidence=schema_result.confidence,
                        weight=get_provider_weight(provider_name),
                        location_type=schema_result.location_type,
                        raw_response=schema_result.raw_response,
                        source_result=schema_result,
                    ))
            else:
                # Remote provider: upsert into geocoding_results
                is_match = schema_result.confidence > 0.0
                ewkt_point = None
                latitude = None
                longitude = None
                location_type_value = None

                if is_match:
                    ewkt_point = f"SRID=4326;POINT({schema_result.lng} {schema_result.lat})"
                    latitude = schema_result.lat
                    longitude = schema_result.lng
                    location_type_value = schema_result.location_type

                stmt = (
                    pg_insert(GeocodingResultORM)
                    .values(
                        address_id=address.id,
                        provider_name=provider_name,
                        location=ewkt_point,
                        latitude=latitude,
                        longitude=longitude,
                        location_type=location_type_value,
                        confidence=schema_result.confidence,
                        raw_response=schema_result.raw_response,
                    )
                    .on_conflict_do_update(
                        constraint="uq_geocoding_address_provider",
                        set_={
                            "location": ewkt_point,
                            "latitude": latitude,
                            "longitude": longitude,
                            "location_type": location_type_value,
                            "confidence": schema_result.confidence,
                            "raw_response": schema_result.raw_response,
                        },
                    )
                    .returning(GeocodingResultORM.id)
                )
                upsert_result = await db.execute(stmt)
                result_id = upsert_result.scalar_one()

                # Re-query full ORM object
                orm_row_result = await db.execute(
                    select(GeocodingResultORM).where(GeocodingResultORM.id == result_id)
                )
                orm_row = orm_row_result.scalars().first()
                if orm_row:
                    new_results.append(orm_row)

                if is_match:
                    candidates.append(ProviderCandidate(
                        provider_name=provider_name,
                        lat=schema_result.lat,
                        lng=schema_result.lng,
                        confidence=schema_result.confidence,
                        weight=get_provider_weight(provider_name),
                        location_type=schema_result.location_type,
                        raw_response=schema_result.raw_response,
                        source_result=schema_result,
                        geocoding_result_id=result_id,
                    ))

        if trace or dry_run:
            cascade_trace.append({
                "stage": "exact_match",
                "providers_called": [k for k, _ in all_provider_items],
                "results_count": len(candidates),
                "ms": round((time.monotonic() - t_stage) * 1000, 1),
            })

        # ----------------------------------------------------------------
        # Early-exit check (D-12)
        # ----------------------------------------------------------------
        skip_fuzzy = any(c.confidence >= 0.80 for c in candidates)

        # ----------------------------------------------------------------
        # Stage 3: Fuzzy match (if not skip_fuzzy and fuzzy_matcher provided)
        # ----------------------------------------------------------------
        t_stage = time.monotonic()

        if not skip_fuzzy and fuzzy_matcher is not None:
            try:
                street_number, street_name, postal_code, _, _ = _parse_input_address(normalized)
                if street_name:
                    fuzzy_result = await asyncio.wait_for(
                        fuzzy_matcher.find_fuzzy_match(
                            street_name,
                            zip_code=postal_code,
                            street_number=street_number,
                        ),
                        timeout=settings.fuzzy_match_timeout_ms / 1000,
                    )
                    if fuzzy_result is not None and fuzzy_result.lat is not None:
                        # Effective weight scales by (fuzzy_confidence / 0.80) (D-09)
                        provider_weight = get_provider_weight(fuzzy_result.source)
                        effective_weight = provider_weight * (fuzzy_result.confidence / 0.80)
                        candidates.append(ProviderCandidate(
                            provider_name=f"fuzzy_{fuzzy_result.source}",
                            lat=fuzzy_result.lat,
                            lng=fuzzy_result.lng,
                            confidence=fuzzy_result.confidence,
                            weight=effective_weight,
                            is_fuzzy=True,
                            source_result=fuzzy_result,
                        ))
                        if trace or dry_run:
                            cascade_trace.append({
                                "stage": "fuzzy_match",
                                "matched_street": fuzzy_result.street_name,
                                "source": fuzzy_result.source,
                                "score": fuzzy_result.score,
                                "confidence": fuzzy_result.confidence,
                                "ms": round((time.monotonic() - t_stage) * 1000, 1),
                            })
                    else:
                        if trace or dry_run:
                            cascade_trace.append({
                                "stage": "fuzzy_match",
                                "matched_street": None,
                                "ms": round((time.monotonic() - t_stage) * 1000, 1),
                            })
            except asyncio.TimeoutError:
                logger.warning(
                    "CascadeOrchestrator: fuzzy stage timed out after {}ms",
                    settings.fuzzy_match_timeout_ms,
                )
                if trace or dry_run:
                    cascade_trace.append({
                        "stage": "fuzzy_match",
                        "timeout": True,
                        "ms": settings.fuzzy_match_timeout_ms,
                    })

        # ----------------------------------------------------------------
        # Stage 4: Consensus scoring (CONS-01) — always runs (D-13)
        # ----------------------------------------------------------------
        t_stage = time.monotonic()

        winning_cluster, scored_candidates = run_consensus(candidates)

        outlier_providers: set[str] = {
            c.provider_name for c in scored_candidates if c.is_outlier
        }

        # Determine set_by_stage
        set_by_stage: str | None = None
        if winning_cluster is not None:
            if len(scored_candidates) == 1:
                set_by_stage = "single_provider"
            elif any(m.is_fuzzy for m in winning_cluster.members):
                set_by_stage = "fuzzy_consensus"
            else:
                set_by_stage = "exact_match_consensus"

        if trace or dry_run:
            cascade_trace.append({
                "stage": "consensus",
                "candidates_count": len(scored_candidates),
                "winning_cluster_size": len(winning_cluster.members) if winning_cluster else 0,
                "winning_cluster_weight": winning_cluster.total_weight if winning_cluster else 0.0,
                "set_by_stage": set_by_stage,
                "outlier_providers": list(outlier_providers),
                "ms": round((time.monotonic() - t_stage) * 1000, 1),
            })

        # ----------------------------------------------------------------
        # Stage 5: Auto-set official (CONS-04)
        # ----------------------------------------------------------------
        t_stage = time.monotonic()

        official_result: GeocodingResultORM | None = None
        would_set_official: ProviderCandidate | None = None
        official_loaded: bool = False  # track if official already loaded from DB
        skip_single_low_conf: bool = False

        if winning_cluster is not None:
            # For weighted centroid winner, find the member closest to centroid
            best_candidate = min(
                winning_cluster.members,
                key=lambda m: haversine_m(
                    m.lat, m.lng,
                    winning_cluster.centroid_lat, winning_cluster.centroid_lng,
                ),
            )

            # D-11: single result with confidence < 0.80 skips auto-set
            skip_single_low_conf = (
                len(scored_candidates) == 1 and best_candidate.confidence < 0.80
            )

            if skip_single_low_conf:
                logger.debug(
                    "CascadeOrchestrator: single result confidence={:.2f} < 0.80 — skipping auto-set",
                    best_candidate.confidence,
                )
            else:
                # D-22: check for existing admin override before updating OfficialGeocoding
                admin_check_result = await db.execute(
                    select(GeocodingResultORM)
                    .join(OfficialGeocoding, OfficialGeocoding.geocoding_result_id == GeocodingResultORM.id)
                    .where(
                        OfficialGeocoding.address_id == address.id,
                        GeocodingResultORM.provider_name == "admin_override",
                    )
                )
                existing_admin = admin_check_result.scalars().first()

                # Also check AdminOverride table directly
                if existing_admin is None:
                    admin_override_check = await db.execute(
                        select(AdminOverride).where(AdminOverride.address_id == address.id)
                    )
                    existing_admin = admin_override_check.scalars().first()

                if existing_admin is not None:
                    logger.debug(
                        "CascadeOrchestrator: admin override exists for address_id={} — skipping auto-set",
                        address.id,
                    )
                    # Load current official result to return (then mark as loaded)
                    official_result = await self._get_official(db, address.id)
                    official_loaded = True
                else:
                    # Determine geocoding_result_id for the best_candidate
                    geocoding_result_id = best_candidate.geocoding_result_id

                    if geocoding_result_id is None:
                        # Local or fuzzy candidate — need to persist a GeocodingResult row first
                        ewkt_point = (
                            f"SRID=4326;POINT({best_candidate.lng} {best_candidate.lat})"
                        )
                        persist_stmt = (
                            pg_insert(GeocodingResultORM)
                            .values(
                                address_id=address.id,
                                provider_name=best_candidate.provider_name,
                                location=ewkt_point,
                                latitude=best_candidate.lat,
                                longitude=best_candidate.lng,
                                location_type=best_candidate.location_type,
                                confidence=best_candidate.confidence,
                                raw_response=best_candidate.raw_response or {},
                            )
                            .on_conflict_do_update(
                                constraint="uq_geocoding_address_provider",
                                set_={
                                    "location": ewkt_point,
                                    "latitude": best_candidate.lat,
                                    "longitude": best_candidate.lng,
                                    "location_type": best_candidate.location_type,
                                    "confidence": best_candidate.confidence,
                                    "raw_response": best_candidate.raw_response or {},
                                },
                            )
                            .returning(GeocodingResultORM.id)
                        )
                        persist_result = await db.execute(persist_stmt)
                        geocoding_result_id = persist_result.scalar_one()

                    if dry_run:
                        # Populate would_set_official, do NOT write OfficialGeocoding
                        best_candidate_with_id = ProviderCandidate(
                            provider_name=best_candidate.provider_name,
                            lat=best_candidate.lat,
                            lng=best_candidate.lng,
                            confidence=best_candidate.confidence,
                            weight=best_candidate.weight,
                            location_type=best_candidate.location_type,
                            raw_response=best_candidate.raw_response,
                            is_fuzzy=best_candidate.is_fuzzy,
                            geocoding_result_id=geocoding_result_id,
                        )
                        would_set_official = best_candidate_with_id
                    else:
                        # Upsert OfficialGeocoding with set_by_stage (D-22, on_conflict_do_update)
                        official_stmt = (
                            pg_insert(OfficialGeocoding)
                            .values(
                                address_id=address.id,
                                geocoding_result_id=geocoding_result_id,
                                set_by_stage=set_by_stage,
                            )
                            .on_conflict_do_update(
                                index_elements=["address_id"],
                                set_={
                                    "geocoding_result_id": geocoding_result_id,
                                    "set_by_stage": set_by_stage,
                                },
                            )
                        )
                        await db.execute(official_stmt)

        if trace or dry_run:
            cascade_trace.append({
                "stage": "auto_set_official",
                "set_by_stage": set_by_stage,
                "dry_run": dry_run,
                "would_set_official": would_set_official.provider_name if would_set_official else None,
                "ms": round((time.monotonic() - t_stage) * 1000, 1),
            })

        # ----------------------------------------------------------------
        # Stage 6: Commit and return
        # ----------------------------------------------------------------
        await db.commit()

        # Reload official after commit if we wrote one (but not if already loaded)
        if (
            winning_cluster is not None
            and not dry_run
            and set_by_stage
            and not skip_single_low_conf
            and not official_loaded
        ):
            official_result = await self._get_official(db, address.id)

        total_ms = round((time.monotonic() - t_total_start) * 1000, 1)
        logger.debug(
            "CascadeOrchestrator: complete — address_hash={} candidates={} "
            "set_by_stage={} total_ms={}",
            address_hash, len(candidates), set_by_stage, total_ms,
        )

        return CascadeResult(
            address_hash=address_hash,
            normalized_address=normalized,
            address=address,
            cache_hit=False,
            results=new_results,
            local_results=local_results,
            official=official_result,
            would_set_official=would_set_official,
            cascade_trace=cascade_trace if (trace or dry_run) else None,
            outlier_providers=outlier_providers,
        )

    async def _get_official(
        self,
        db: AsyncSession,
        address_id: int,
    ) -> GeocodingResultORM | None:
        """Load the OfficialGeocoding result for an address, if one exists."""
        result = await db.execute(
            select(OfficialGeocoding).where(
                OfficialGeocoding.address_id == address_id
            )
        )
        official = result.scalars().first()
        if official is None:
            return None

        gr_result = await db.execute(
            select(GeocodingResultORM).where(
                GeocodingResultORM.id == official.geocoding_result_id
            )
        )
        return gr_result.scalars().first()
