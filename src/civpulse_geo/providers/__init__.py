"""CivPulse geo-api provider plugin system.

Exports the full provider contract surface:
- GeocodingProvider, ValidationProvider: ABCs all providers must implement
- GeocodingResult: canonical result dataclass
- ProviderError and typed subtypes: exception hierarchy for error handling
- load_providers: registry factory for eager instantiation at startup

Usage:
    from civpulse_geo.providers import GeocodingProvider, load_providers
"""
from civpulse_geo.providers.base import GeocodingProvider, ValidationProvider
from civpulse_geo.providers.schemas import GeocodingResult
from civpulse_geo.providers.exceptions import (
    ProviderError,
    ProviderNetworkError,
    ProviderAuthError,
    ProviderRateLimitError,
)
from civpulse_geo.providers.registry import load_providers

__all__ = [
    "GeocodingProvider",
    "ValidationProvider",
    "GeocodingResult",
    "ProviderError",
    "ProviderNetworkError",
    "ProviderAuthError",
    "ProviderRateLimitError",
    "load_providers",
]
