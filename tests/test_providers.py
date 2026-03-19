"""Tests for INFRA-02: provider plugin contract and ABC enforcement.

Tests verify:
- GeocodingProvider ABC: TypeError on instantiation when required methods missing
- ValidationProvider ABC: TypeError on instantiation when required methods missing
- Valid concrete providers instantiate without error
- load_providers({}) returns empty dict
- load_providers with incomplete provider raises TypeError
- ProviderError exception hierarchy (Network, Auth, RateLimit subtypes)
- GeocodingResult dataclass fields and instantiation
"""
import pytest
from civpulse_geo.providers import (
    GeocodingProvider,
    ValidationProvider,
    GeocodingResult,
    ProviderError,
    ProviderNetworkError,
    ProviderAuthError,
    ProviderRateLimitError,
    load_providers,
)


# ---------------------------------------------------------------------------
# Fixture: concrete providers for testing
# ---------------------------------------------------------------------------

class _ConcreteGeocodingProvider(GeocodingProvider):
    """Fully implemented GeocodingProvider for use in positive tests."""

    @property
    def provider_name(self) -> str:
        return "test-geocoder"

    async def geocode(self, address: str) -> GeocodingResult:
        return GeocodingResult(
            lat=32.8407,
            lng=-83.6324,
            location_type="ROOFTOP",
            confidence=0.99,
            raw_response={},
            provider_name=self.provider_name,
        )

    async def batch_geocode(self, addresses: list[str]) -> list[GeocodingResult]:
        return [await self.geocode(a) for a in addresses]


class _ConcreteValidationProvider(ValidationProvider):
    """Fully implemented ValidationProvider for use in positive tests."""

    @property
    def provider_name(self) -> str:
        return "test-validator"

    async def validate(self, address: str) -> dict:
        return {"valid": True, "standardized": address}

    async def batch_validate(self, addresses: list[str]) -> list[dict]:
        return [await self.validate(a) for a in addresses]


# ---------------------------------------------------------------------------
# GeocodingProvider ABC enforcement
# ---------------------------------------------------------------------------

class TestGeocodingProviderABC:
    def test_missing_geocode_raises_type_error(self):
        """Omitting geocode() raises TypeError on instantiation."""
        class MissingGeocode(GeocodingProvider):
            @property
            def provider_name(self) -> str:
                return "bad"

            async def batch_geocode(self, addresses: list[str]) -> list[GeocodingResult]:
                return []

        with pytest.raises(TypeError):
            MissingGeocode()

    def test_missing_provider_name_raises_type_error(self):
        """Omitting provider_name property raises TypeError on instantiation."""
        class MissingProviderName(GeocodingProvider):
            async def geocode(self, address: str) -> GeocodingResult:
                pass

            async def batch_geocode(self, addresses: list[str]) -> list[GeocodingResult]:
                return []

        with pytest.raises(TypeError):
            MissingProviderName()

    def test_missing_batch_geocode_raises_type_error(self):
        """Omitting batch_geocode() raises TypeError on instantiation."""
        class MissingBatchGeocode(GeocodingProvider):
            @property
            def provider_name(self) -> str:
                return "bad"

            async def geocode(self, address: str) -> GeocodingResult:
                pass

        with pytest.raises(TypeError):
            MissingBatchGeocode()

    def test_all_methods_missing_raises_type_error(self):
        """Omitting all abstract methods raises TypeError."""
        class EmptyProvider(GeocodingProvider):
            pass

        with pytest.raises(TypeError):
            EmptyProvider()

    def test_valid_concrete_provider_instantiates(self):
        """A fully implemented concrete GeocodingProvider instantiates without error."""
        provider = _ConcreteGeocodingProvider()
        assert provider is not None
        assert provider.provider_name == "test-geocoder"

    def test_abstract_methods_listed(self):
        """GeocodingProvider has the expected abstract methods."""
        abstract_methods = GeocodingProvider.__abstractmethods__
        assert "geocode" in abstract_methods
        assert "batch_geocode" in abstract_methods
        assert "provider_name" in abstract_methods


# ---------------------------------------------------------------------------
# ValidationProvider ABC enforcement
# ---------------------------------------------------------------------------

class TestValidationProviderABC:
    def test_missing_validate_raises_type_error(self):
        """Omitting validate() raises TypeError on instantiation."""
        class MissingValidate(ValidationProvider):
            @property
            def provider_name(self) -> str:
                return "bad"

            async def batch_validate(self, addresses: list[str]) -> list[dict]:
                return []

        with pytest.raises(TypeError):
            MissingValidate()

    def test_missing_provider_name_raises_type_error(self):
        """Omitting provider_name property raises TypeError on instantiation."""
        class MissingProviderName(ValidationProvider):
            async def validate(self, address: str) -> dict:
                return {}

            async def batch_validate(self, addresses: list[str]) -> list[dict]:
                return []

        with pytest.raises(TypeError):
            MissingProviderName()

    def test_valid_concrete_validation_provider_instantiates(self):
        """A fully implemented concrete ValidationProvider instantiates without error."""
        provider = _ConcreteValidationProvider()
        assert provider is not None
        assert provider.provider_name == "test-validator"


# ---------------------------------------------------------------------------
# Provider registry
# ---------------------------------------------------------------------------

class TestProviderRegistry:
    def test_empty_dict_returns_empty_registry(self):
        """load_providers({}) returns an empty dict."""
        result = load_providers({})
        assert result == {}
        assert isinstance(result, dict)

    def test_valid_provider_is_registered(self):
        """load_providers with a valid provider class returns instantiated provider."""
        result = load_providers({"geocoder": _ConcreteGeocodingProvider})
        assert "geocoder" in result
        assert isinstance(result["geocoder"], _ConcreteGeocodingProvider)

    def test_incomplete_provider_raises_type_error(self):
        """load_providers raises TypeError when a provider class is incomplete."""
        class IncompleteProvider(GeocodingProvider):
            # Missing geocode, batch_geocode, and provider_name
            pass

        with pytest.raises(TypeError):
            load_providers({"bad": IncompleteProvider})

    def test_multiple_providers_registered(self):
        """load_providers can register multiple providers at once."""
        result = load_providers({
            "geocoder": _ConcreteGeocodingProvider,
            "validator": _ConcreteValidationProvider,
        })
        assert len(result) == 2
        assert "geocoder" in result
        assert "validator" in result

    def test_provider_is_eagerly_instantiated(self):
        """Providers are instances, not classes, after load_providers."""
        result = load_providers({"geocoder": _ConcreteGeocodingProvider})
        assert isinstance(result["geocoder"], GeocodingProvider)
        # Should be an instance, not the class itself
        assert result["geocoder"] is not _ConcreteGeocodingProvider


# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------

class TestExceptionHierarchy:
    def test_provider_network_error_is_provider_error(self):
        """ProviderNetworkError is a subclass of ProviderError."""
        assert issubclass(ProviderNetworkError, ProviderError)

    def test_provider_auth_error_is_provider_error(self):
        """ProviderAuthError is a subclass of ProviderError."""
        assert issubclass(ProviderAuthError, ProviderError)

    def test_provider_rate_limit_error_is_provider_error(self):
        """ProviderRateLimitError is a subclass of ProviderError."""
        assert issubclass(ProviderRateLimitError, ProviderError)

    def test_provider_error_is_exception(self):
        """ProviderError is a subclass of Exception."""
        assert issubclass(ProviderError, Exception)

    def test_provider_network_error_can_be_raised(self):
        """ProviderNetworkError can be raised and caught as ProviderError."""
        with pytest.raises(ProviderError):
            raise ProviderNetworkError("Connection refused")

    def test_provider_auth_error_can_be_raised(self):
        """ProviderAuthError can be raised and caught as ProviderError."""
        with pytest.raises(ProviderError):
            raise ProviderAuthError("Invalid API key")

    def test_provider_rate_limit_error_can_be_raised(self):
        """ProviderRateLimitError can be raised and caught as ProviderError."""
        with pytest.raises(ProviderError):
            raise ProviderRateLimitError("Rate limit exceeded")

    def test_exception_message_preserved(self):
        """Exception message is preserved when raising provider errors."""
        msg = "Test error message"
        exc = ProviderNetworkError(msg)
        assert str(exc) == msg


# ---------------------------------------------------------------------------
# GeocodingResult dataclass
# ---------------------------------------------------------------------------

class TestGeocodingResultSchema:
    def test_geocoding_result_instantiation(self):
        """GeocodingResult can be instantiated with all required fields."""
        result = GeocodingResult(
            lat=32.8407,
            lng=-83.6324,
            location_type="ROOFTOP",
            confidence=0.99,
            raw_response={"source": "test"},
            provider_name="test-provider",
        )
        assert result is not None

    def test_lat_field(self):
        """GeocodingResult has lat field with correct value."""
        result = GeocodingResult(
            lat=32.8407, lng=-83.6324, location_type="ROOFTOP",
            confidence=0.99, raw_response={}, provider_name="test",
        )
        assert result.lat == 32.8407

    def test_lng_field(self):
        """GeocodingResult has lng field with correct value."""
        result = GeocodingResult(
            lat=32.8407, lng=-83.6324, location_type="ROOFTOP",
            confidence=0.99, raw_response={}, provider_name="test",
        )
        assert result.lng == -83.6324

    def test_location_type_field(self):
        """GeocodingResult has location_type field with correct value."""
        result = GeocodingResult(
            lat=32.8407, lng=-83.6324, location_type="RANGE_INTERPOLATED",
            confidence=0.75, raw_response={}, provider_name="test",
        )
        assert result.location_type == "RANGE_INTERPOLATED"

    def test_confidence_field(self):
        """GeocodingResult has confidence field."""
        result = GeocodingResult(
            lat=0.0, lng=0.0, location_type="APPROXIMATE",
            confidence=0.5, raw_response={}, provider_name="test",
        )
        assert result.confidence == 0.5

    def test_raw_response_field(self):
        """GeocodingResult has raw_response field accepting a dict."""
        raw = {"key": "value", "nested": {"a": 1}}
        result = GeocodingResult(
            lat=0.0, lng=0.0, location_type="APPROXIMATE",
            confidence=0.5, raw_response=raw, provider_name="test",
        )
        assert result.raw_response == raw

    def test_provider_name_field(self):
        """GeocodingResult has provider_name field."""
        result = GeocodingResult(
            lat=0.0, lng=0.0, location_type="APPROXIMATE",
            confidence=0.5, raw_response={}, provider_name="census",
        )
        assert result.provider_name == "census"
