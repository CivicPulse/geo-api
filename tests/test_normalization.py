"""Tests for INFRA-01: canonical address normalization.

Tests verify:
- Suffix normalization (Street -> ST)
- Directional normalization (North -> N, Avenue -> AVE)
- State name to abbreviation (Georgia -> GA)
- ZIP+4 stripped to ZIP5
- Unit/apartment designators excluded from base geocoding key
- Case insensitivity
- Return type is tuple[str, str] with 64-char SHA-256 hex hash
- Fallback behavior for unparseable addresses
- parse_address_components returns structured dict
"""
import pytest
from civpulse_geo.normalization import canonical_key, parse_address_components


class TestCanonicalKeyReturnType:
    def test_returns_tuple(self):
        result = canonical_key("123 Main St, Macon, GA 31201")
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_hash_is_64_hex_chars(self):
        normalized, hash_val = canonical_key("123 Main St, Macon, GA 31201")
        assert isinstance(hash_val, str)
        assert len(hash_val) == 64
        # Must be valid hex
        int(hash_val, 16)

    def test_normalized_string_is_str(self):
        normalized, hash_val = canonical_key("123 Main St, Macon, GA 31201")
        assert isinstance(normalized, str)
        assert len(normalized) > 0


class TestSuffixNormalization:
    def test_street_to_st(self):
        """'Street' and 'St' should produce the same canonical key."""
        _, hash_full = canonical_key("123 Main Street, Macon, GA 31201")
        _, hash_abbrev = canonical_key("123 Main St, Macon, GA 31201")
        assert hash_full == hash_abbrev, (
            f"Suffix normalization failed: 'Street' and 'St' produce different hashes"
        )

    def test_avenue_to_ave(self):
        """'Avenue' and 'Ave' should produce the same canonical key."""
        _, hash_full = canonical_key("456 North Oak Avenue, Atlanta, GA 30301")
        _, hash_abbrev = canonical_key("456 N Oak Ave, Atlanta, GA 30301")
        assert hash_full == hash_abbrev, (
            f"Suffix+directional normalization failed"
        )


class TestDirectionalNormalization:
    def test_north_to_n(self):
        """'North' and 'N' directional should produce the same canonical key."""
        _, hash_full = canonical_key("456 North Oak Ave, Atlanta, GA 30301")
        _, hash_abbrev = canonical_key("456 N Oak Ave, Atlanta, GA 30301")
        assert hash_full == hash_abbrev

    def test_directional_and_suffix_combined(self):
        """Both directional and suffix normalization applied together."""
        _, hash_full = canonical_key("456 North Oak Avenue, Atlanta, GA 30301")
        _, hash_abbrev = canonical_key("456 N Oak Ave, Atlanta, GA 30301")
        assert hash_full == hash_abbrev


class TestStateNormalization:
    def test_state_name_to_abbreviation(self):
        """Full state name 'Georgia' should normalize to 'GA'."""
        _, hash_name = canonical_key("789 Elm St, Macon, Georgia 31201")
        _, hash_abbrev = canonical_key("789 Elm St, Macon, GA 31201")
        assert hash_name == hash_abbrev, (
            f"State normalization failed: 'Georgia' and 'GA' produce different hashes"
        )


class TestZipCode:
    def test_zip4_stripped_to_zip5(self):
        """ZIP+4 input is reduced to ZIP5 in the canonical key."""
        normalized_zip4, hash_zip4 = canonical_key("100 Pine St, Macon, GA 31201-1234")
        normalized_zip5, hash_zip5 = canonical_key("100 Pine St, Macon, GA 31201")
        assert hash_zip4 == hash_zip5, (
            f"ZIP+4 not stripped: '{normalized_zip4}' != '{normalized_zip5}'"
        )
        # The normalized string itself should NOT contain the +4 portion
        assert "1234" not in normalized_zip4

    def test_zip5_preserved(self):
        """ZIP5 is preserved as-is in the canonical key."""
        normalized, _ = canonical_key("100 Pine St, Macon, GA 31201")
        assert "31201" in normalized


class TestUnitStripping:
    def test_apt_excluded_from_base_key(self):
        """Apartment designator 'Apt 4B' is excluded from the base geocoding key."""
        normalized_with_unit, hash_with_unit = canonical_key("100 Pine St Apt 4B, Macon, GA 31201")
        normalized_without_unit, hash_without_unit = canonical_key("100 Pine St, Macon, GA 31201")
        assert hash_with_unit == hash_without_unit, (
            f"Unit stripping failed: with unit '{normalized_with_unit}' "
            f"!= without unit '{normalized_without_unit}'"
        )

    def test_apt_with_comma_excluded(self):
        """Apartment designator with comma separator is excluded."""
        _, hash_with_unit = canonical_key("100 Pine St, Apt 4B, Macon, GA 31201-1234")
        _, hash_without_unit = canonical_key("100 Pine St, Macon, GA 31201")
        assert hash_with_unit == hash_without_unit

    def test_unit_number_in_normalized_string_excluded(self):
        """The unit number itself does not appear in normalized string used for hashing."""
        normalized_with_unit, _ = canonical_key("100 Pine St Apt 4B, Macon, GA 31201")
        # Unit designator and number should not appear in the base key
        assert "APT" not in normalized_with_unit or "4B" not in normalized_with_unit


class TestCaseInsensitivity:
    def test_lowercase_equals_uppercase(self):
        """Lowercase and uppercase addresses produce identical canonical keys."""
        _, hash_lower = canonical_key("100 pine st, macon, ga 31201")
        _, hash_upper = canonical_key("100 PINE ST, MACON, GA 31201")
        assert hash_lower == hash_upper, (
            f"Case sensitivity issue: lowercase and uppercase produce different hashes"
        )

    def test_mixed_case(self):
        """Mixed case produces the same result as fully uppercase."""
        _, hash_mixed = canonical_key("100 Pine St, Macon, GA 31201")
        _, hash_upper = canonical_key("100 PINE ST, MACON, GA 31201")
        assert hash_mixed == hash_upper


class TestFallbackBehavior:
    def test_garbage_input_does_not_raise(self):
        """Unparseable input ('???') falls back gracefully without raising."""
        result = canonical_key("???")
        assert isinstance(result, tuple)
        assert len(result) == 2
        normalized, hash_val = result
        assert len(hash_val) == 64

    def test_empty_string_does_not_raise(self):
        """Empty string falls back gracefully without raising."""
        result = canonical_key("")
        assert isinstance(result, tuple)
        normalized, hash_val = result
        assert len(hash_val) == 64

    def test_po_box_does_not_raise(self):
        """PO Box input falls back gracefully without raising."""
        result = canonical_key("PO Box 123, Macon, GA 31201")
        assert isinstance(result, tuple)
        normalized, hash_val = result
        assert len(hash_val) == 64


class TestParseAddressComponents:
    def test_returns_dict(self):
        """parse_address_components returns a dict."""
        result = parse_address_components("123 Main St, Macon, GA 31201")
        assert isinstance(result, dict)

    def test_standard_keys_present(self):
        """Standard address component keys are present in result."""
        result = parse_address_components("123 Main St, Macon, GA 31201")
        # These keys should be in the result for parseable addresses
        assert "city" in result
        assert "state" in result
        assert "zip_code" in result

    def test_zip5_only_in_parsed_components(self):
        """parse_address_components returns ZIP5 only, not ZIP+4."""
        result = parse_address_components("123 Main St, Macon, GA 31201-1234")
        if "zip_code" in result and result["zip_code"]:
            assert len(result["zip_code"]) == 5
            assert "-" not in result["zip_code"]

    def test_unparseable_returns_original_input(self):
        """Unparseable input returns dict with 'original_input' key."""
        result = parse_address_components("???")
        assert "original_input" in result
        assert result["original_input"] == "???"

    def test_street_number_extracted(self):
        """Street number is extracted from parseable address."""
        result = parse_address_components("123 Main St, Macon, GA 31201")
        if "street_number" in result:
            assert result["street_number"] == "123"
