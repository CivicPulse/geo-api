"""Unit tests for ScourgifyValidationProvider.

TDD approach — tests are written against the interface spec before implementation.

Tests verify:
- provider_name property returns "scourgify"
- validate() returns ValidationResult with correct normalized components
- USPS Pub 28 abbreviations applied: "Road" -> "RD", "Georgia" -> "GA"
- APT/unit designators extracted to address_line_2
- ZIP+4 postal codes preserved in full (e.g. "31201-5678")
- confidence is always 0.3 for successful normalization (parse-only, not address-verified)
- delivery_point_verified is always False
- Unparseable addresses (PO Box, gibberish) raise ProviderError
- original_input echoes back the raw input string
- normalized_address contains all component parts
- batch_validate processes multiple addresses in order
"""
import pytest

from civpulse_geo.providers.scourgify import ScourgifyValidationProvider
from civpulse_geo.providers.exceptions import ProviderError
from civpulse_geo.providers.schemas import ValidationResult


@pytest.fixture
def provider():
    return ScourgifyValidationProvider()


async def test_provider_name(provider):
    """provider_name property returns 'scourgify'."""
    assert provider.provider_name == "scourgify"


async def test_validate_freeform(provider):
    """Basic address validation returns normalized components."""
    result = await provider.validate("626 Arlington Pl, Macon, GA 31201")
    assert result.address_line_1 == "626 ARLINGTON PL"
    assert result.city == "MACON"
    assert result.state == "GA"
    assert result.postal_code == "31201"
    assert result.confidence == 0.3
    assert result.delivery_point_verified is False
    assert result.provider_name == "scourgify"


async def test_usps_abbreviations(provider):
    """USPS Pub 28 abbreviations applied: Road->RD, Georgia->GA."""
    result = await provider.validate("123 Main Road, Macon, Georgia 31201")
    assert "MAIN RD" in result.address_line_1
    assert result.state == "GA"


async def test_unit_in_address_line_2(provider):
    """Unit designators extracted to address_line_2."""
    result = await provider.validate("100 Pine Street Apt 4B, Macon, GA 31201")
    assert result.address_line_1 == "100 PINE ST"
    assert result.address_line_2 == "APT 4B"


async def test_zip_plus_4_preserved(provider):
    """ZIP+4 postal codes preserved in full."""
    result = await provider.validate("789 Elm Rd, Macon, Georgia 31201-5678")
    assert result.postal_code == "31201-5678"


async def test_confidence_always_0_3(provider):
    """All successful validations return confidence=0.3 (parse-only, not address-verified)."""
    result = await provider.validate("626 Arlington Pl, Macon, GA 31201")
    assert result.confidence == 0.3


async def test_dpv_always_false(provider):
    """delivery_point_verified is always False for scourgify."""
    result = await provider.validate("626 Arlington Pl, Macon, GA 31201")
    assert result.delivery_point_verified is False


async def test_provider_name_field_in_result(provider):
    """ValidationResult.provider_name is 'scourgify'."""
    result = await provider.validate("626 Arlington Pl, Macon, GA 31201")
    assert result.provider_name == "scourgify"


async def test_unparseable_raises_provider_error(provider):
    """PO Box addresses raise ProviderError (cannot be normalized for delivery point)."""
    with pytest.raises(ProviderError):
        await provider.validate("PO Box 123, Macon, GA 31201")


async def test_gibberish_raises_provider_error(provider):
    """Completely unparseable input raises ProviderError."""
    with pytest.raises(ProviderError):
        await provider.validate("not a real address at all")


async def test_original_input_echoed(provider):
    """ValidationResult.original_input is the raw input string."""
    raw = "626 Arlington Pl, Macon, GA 31201"
    result = await provider.validate(raw)
    assert result.original_input == raw


async def test_normalized_address_full_string(provider):
    """normalized_address contains all components concatenated."""
    result = await provider.validate("123 Main Road, Macon, Georgia 31201")
    assert "123 MAIN RD" in result.normalized_address
    assert "MACON" in result.normalized_address
    assert "GA" in result.normalized_address


async def test_batch_validate(provider):
    """batch_validate returns results in same order as input."""
    addresses = [
        "626 Arlington Pl, Macon, GA 31201",
        "123 Main Road, Macon, Georgia 31201",
        "100 Pine Street Apt 4B, Macon, GA 31201",
    ]
    results = await provider.batch_validate(addresses)
    assert len(results) == 3
    assert results[0].address_line_1 == "626 ARLINGTON PL"
    assert "MAIN RD" in results[1].address_line_1


async def test_batch_validate_returns_validation_results(provider):
    """batch_validate returns ValidationResult instances."""
    addresses = ["626 Arlington Pl, Macon, GA 31201"]
    results = await provider.batch_validate(addresses)
    assert isinstance(results[0], ValidationResult)


async def test_returns_validation_result_type(provider):
    """validate() returns a ValidationResult dataclass instance."""
    result = await provider.validate("626 Arlington Pl, Macon, GA 31201")
    assert isinstance(result, ValidationResult)


async def test_address_line_2_none_when_no_unit(provider):
    """address_line_2 is None when no secondary designator present."""
    result = await provider.validate("626 Arlington Pl, Macon, GA 31201")
    assert result.address_line_2 is None
