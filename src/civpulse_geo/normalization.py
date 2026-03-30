"""Canonical address normalization for CivPulse geo-api.

Implements INFRA-01: input addresses are normalized to a canonical form
before cache lookup to maximize cache hit rate.

Two-tier key design:
- Base geocoding key: no unit designator, ZIP5 only — used for geocoding cache lookups
- Full address: includes unit for storage/matching but inherits base geocode

Both the normalized string (human-readable) and SHA-256 hash are returned
so callers can store one and use the other for fast lookups.
"""
import hashlib
import re

from scourgify import normalize_address_record
from scourgify.exceptions import (
    AmbiguousAddressError,
    AddressNormalizationError,
    UnParseableAddressError,
    IncompleteAddressError,
)

# Unit designator keywords per USPS Pub 28 Table C2
# When found in address_line_1, everything from this keyword onward is the unit portion.
_UNIT_KEYWORDS = frozenset([
    "APT", "STE", "UNIT", "#", "BLDG", "FL", "RM", "DEPT",
    "BSMT", "FRNT", "REAR", "SIDE", "LOWR", "UPPR", "LOT",
    "SPC", "TRLR", "SLIP", "PH", "PIER", "OFC", "STOP", "HNGR",
])

# Pattern to detect and split unit designators from the base address line.
# Matches: word boundary + unit keyword + optional number/letter
_UNIT_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in sorted(_UNIT_KEYWORDS, key=len, reverse=True)) + r")\b.*$",
    re.IGNORECASE,
)


def _strip_unit(address_line_1: str) -> str:
    """Remove unit designator and everything after it from an address line.

    Handles both comma-separated ('123 Main St, Apt 4B') and
    space-separated ('123 Main St Apt 4B') unit designators.
    """
    # First strip after comma if a unit keyword follows a comma
    comma_match = re.split(r",\s*", address_line_1)
    if len(comma_match) > 1:
        # Check if the second+ parts start with a unit keyword
        base = comma_match[0].strip()
        for part in comma_match[1:]:
            first_word = part.strip().split()[0].upper() if part.strip() else ""
            if first_word in _UNIT_KEYWORDS or first_word.lstrip("#") == "":
                # This part is a unit — stop here
                return base
    # Fall back to inline unit stripping
    result = _UNIT_PATTERN.sub("", address_line_1).strip()
    # Remove trailing comma or whitespace left behind
    return result.rstrip(", ").strip()


def _zip5(postal_code: str | None) -> str:
    """Extract ZIP5 from a postal code, stripping ZIP+4 suffix."""
    if not postal_code:
        return ""
    # Take only first 5 digits
    digits = re.sub(r"[^\d]", "", postal_code)
    return digits[:5] if digits else ""


def _fallback_normalize(freeform: str) -> str:
    """Simple normalization fallback for addresses scourgify cannot parse.

    Uppercases, collapses whitespace, and removes punctuation except hyphens.
    Returns a normalized string (not a dict) for use in canonical_key.
    """
    normalized = freeform.upper().strip()
    # Remove punctuation except hyphens and spaces
    normalized = re.sub(r"[^\w\s\-]", "", normalized)
    # Collapse whitespace
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def canonical_key(freeform: str) -> tuple[str, str]:
    """Return (normalized_string, sha256_hex) for a freeform address.

    The normalized string is built from USPS Pub 28 standardized components:
    - base address line (unit designators removed)
    - city
    - state abbreviation
    - ZIP5 only (never ZIP+4)

    On success with scourgify: fully USPS-normalized key.
    On scourgify failure: falls back to uppercase + whitespace normalization.

    Args:
        freeform: Freeform address string to normalize.

    Returns:
        Tuple of (normalized_string, sha256_hex_digest).
        sha256_hex_digest is always 64 lowercase hex characters.
    """
    try:
        parsed = normalize_address_record(freeform)
        # scourgify returns keys: address_line_1, address_line_2, city, state, postal_code
        # address_line_1 contains the street address (may include unit)
        # address_line_2 is typically None or secondary designator
        address_line_1 = (parsed.get("address_line_1") or "").strip()
        city = (parsed.get("city") or "").strip().upper()
        state = (parsed.get("state") or "").strip().upper()
        postal = _zip5(parsed.get("postal_code"))

        # Strip unit from address_line_1 to get base geocoding key
        base_address = _strip_unit(address_line_1).upper()

        # Build canonical string
        parts = [p for p in [base_address, city, state, postal] if p]
        normalized = " ".join(parts)
        # Collapse any extra whitespace
        normalized = re.sub(r"\s+", " ", normalized).strip()

    except (AmbiguousAddressError, AddressNormalizationError,
            UnParseableAddressError, IncompleteAddressError, Exception):
        # Fallback: simple uppercase + whitespace normalization
        normalized = _fallback_normalize(freeform)

    hash_val = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return normalized, hash_val


def parse_address_components(freeform: str) -> dict:
    """Parse a freeform address into structured components.

    Attempts USPS Pub 28 normalization via scourgify, extracting:
    - street_number, street_name, street_suffix
    - street_predirection, street_postdirection
    - unit_type, unit_number
    - city, state, zip_code (ZIP5 only)

    On parse failure, returns dict with 'original_input' key only.

    Args:
        freeform: Freeform address string to parse.

    Returns:
        Dict with address components. Keys always present: city, state, zip_code
        on success; 'original_input' only on failure.
    """
    try:
        parsed = normalize_address_record(freeform)
        address_line_1 = (parsed.get("address_line_1") or "").strip()

        # Parse street components from address_line_1
        # Typical scourgify output: "123 N MAIN ST" or "123 N MAIN ST APT 4B"
        components = _parse_address_line_1(address_line_1)

        city = (parsed.get("city") or "").strip().upper() or None
        state = (parsed.get("state") or "").strip().upper() or None
        zip_code = _zip5(parsed.get("postal_code")) or None

        return {
            "street_number": components.get("street_number"),
            "street_name": components.get("street_name"),
            "street_suffix": components.get("street_suffix"),
            "street_predirection": components.get("street_predirection"),
            "street_postdirection": components.get("street_postdirection"),
            "unit_type": components.get("unit_type"),
            "unit_number": components.get("unit_number"),
            "city": city,
            "state": state,
            "zip_code": zip_code,
        }

    except (AmbiguousAddressError, AddressNormalizationError,
            UnParseableAddressError, IncompleteAddressError, Exception):
        return {"original_input": freeform}


def _parse_address_line_1(address_line_1: str) -> dict:
    """Parse scourgify-normalized address_line_1 into subcomponents.

    scourgify has already applied USPS Pub 28 abbreviations, so we parse
    the normalized form. Typical format: "123 N MAIN ST APT 4B"

    Returns dict with: street_number, street_name, street_suffix,
    street_predirection, street_postdirection, unit_type, unit_number.
    """
    result: dict = {
        "street_number": None,
        "street_name": None,
        "street_suffix": None,
        "street_predirection": None,
        "street_postdirection": None,
        "unit_type": None,
        "unit_number": None,
    }

    if not address_line_1:
        return result

    tokens = address_line_1.upper().split()
    if not tokens:
        return result

    idx = 0

    # Token 1: street number (digits)
    if tokens[idx].rstrip(",").isdigit():
        result["street_number"] = tokens[idx].rstrip(",")
        idx += 1

    if idx >= len(tokens):
        return result

    # Token 2 (optional): pre-directional
    predirections = {"N", "S", "E", "W", "NE", "NW", "SE", "SW",
                     "NORTH", "SOUTH", "EAST", "WEST", "NORTHEAST",
                     "NORTHWEST", "SOUTHEAST", "SOUTHWEST"}
    if tokens[idx] in predirections:
        result["street_predirection"] = tokens[idx]
        idx += 1

    if idx >= len(tokens):
        return result

    # Detect unit keyword position
    unit_start_idx = None
    for i in range(idx, len(tokens)):
        tok = tokens[i].rstrip(",")
        if tok in _UNIT_KEYWORDS:
            unit_start_idx = i
            break

    # Tokens before unit_start_idx (or end): street name + suffix
    end_idx = unit_start_idx if unit_start_idx is not None else len(tokens)
    street_tokens = [t.rstrip(",") for t in tokens[idx:end_idx]]

    # Suffix abbreviations (USPS Pub 28 common ones)
    _SUFFIXES = {
        "ST", "AVE", "BLVD", "DR", "RD", "CT", "PL", "LN", "WAY",
        "CIR", "TER", "HWY", "PKY", "PKWY", "FWY", "SQ", "LOOP",
        "TRCE", "TRL", "WALK", "ROW", "PASS", "XING", "ALY", "BND",
    }

    suffix = None
    if street_tokens and street_tokens[-1] in _SUFFIXES:
        suffix = street_tokens[-1]
        street_tokens = street_tokens[:-1]

    result["street_suffix"] = suffix
    result["street_name"] = " ".join(street_tokens) if street_tokens else None

    # Unit components
    if unit_start_idx is not None:
        unit_tokens = [t.rstrip(",") for t in tokens[unit_start_idx:]]
        if unit_tokens:
            result["unit_type"] = unit_tokens[0]
        if len(unit_tokens) > 1:
            result["unit_number"] = " ".join(unit_tokens[1:])

    return result
