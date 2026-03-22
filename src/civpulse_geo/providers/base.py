"""Abstract base classes for geocoding and validation providers.

Defines the plugin contract that all concrete providers must implement.
Python ABCs enforce this contract at instantiation time — any class
that omits an abstract method raises TypeError when you call its constructor.

The provider registry (registry.py) eagerly instantiates all configured
providers at startup, converting ABC enforcement from "whenever first used"
to "before any request is served" — satisfying INFRA-02's "at load time" intent.

Design decisions:
- async methods: FastAPI is async-native; provider calls are I/O-bound HTTP
- provider_name as abstract property: identifies results by source in logs/DB
- batch_geocode as separate abstract method: allows providers to use native
  batch APIs (e.g., Census Geocoder batch endpoint) rather than serial calls
"""
import abc

from civpulse_geo.providers.schemas import GeocodingResult


class GeocodingProvider(abc.ABC):
    """Abstract base class for geocoding providers.

    Concrete implementations must provide:
    - provider_name (property): string identifier for this provider
    - geocode(address): single address -> GeocodingResult
    - batch_geocode(addresses): list of addresses -> list of GeocodingResult
    """

    @property
    def is_local(self) -> bool:
        """True for providers that query local staging tables (bypass DB cache).

        Local providers (e.g., openaddresses, nad, tiger) return results directly
        without writing to geocoding_results. Defaults to False for all remote
        providers -- no subclass changes required.
        """
        return False

    @property
    @abc.abstractmethod
    def provider_name(self) -> str:
        """Unique string identifier for this provider.

        Used in GeocodingResult.provider_name, registry keys, and log messages.
        Example: "census", "google", "here"
        """
        ...

    @abc.abstractmethod
    async def geocode(self, address: str) -> GeocodingResult:
        """Geocode a single freeform address.

        Args:
            address: Freeform address string (USPS-normalized recommended).

        Returns:
            GeocodingResult with lat/lng, location_type, confidence,
            raw_response, and provider_name.

        Raises:
            ProviderNetworkError: Provider unreachable.
            ProviderAuthError: Authentication failed.
            ProviderRateLimitError: Rate limit exceeded.
        """
        ...

    @abc.abstractmethod
    async def batch_geocode(self, addresses: list[str]) -> list[GeocodingResult]:
        """Geocode a list of freeform addresses.

        Implementations may use a native batch API endpoint if available,
        or fall back to serial geocode() calls.

        Args:
            addresses: List of freeform address strings.

        Returns:
            List of GeocodingResult in the same order as input.

        Raises:
            ProviderNetworkError, ProviderAuthError, ProviderRateLimitError.
        """
        ...


class ValidationProvider(abc.ABC):
    """Abstract base class for address validation providers.

    Concrete implementations must provide:
    - provider_name (property): string identifier for this provider
    - validate(address): single address -> structured validation result dict
    - batch_validate(addresses): list of addresses -> list of result dicts
    """

    @property
    def is_local(self) -> bool:
        """True for providers that query local staging tables (bypass DB cache).

        Local providers (e.g., openaddresses, nad, tiger) return results directly
        without writing to validation_results. Defaults to False for all remote
        providers -- no subclass changes required.
        """
        return False

    @property
    @abc.abstractmethod
    def provider_name(self) -> str:
        """Unique string identifier for this provider.

        Example: "usps", "lob", "smarty"
        """
        ...

    @abc.abstractmethod
    async def validate(self, address: str) -> dict:
        """Validate a single freeform address.

        Args:
            address: Freeform address string to validate.

        Returns:
            Dict with at minimum: {"valid": bool, "standardized": str | None}.
            Providers may include additional keys (dpv_confirmation, etc.).

        Raises:
            ProviderNetworkError: Provider unreachable.
            ProviderAuthError: Authentication failed.
            ProviderRateLimitError: Rate limit exceeded.
        """
        ...

    @abc.abstractmethod
    async def batch_validate(self, addresses: list[str]) -> list[dict]:
        """Validate a list of freeform addresses.

        Args:
            addresses: List of freeform address strings.

        Returns:
            List of validation result dicts in the same order as input.
        """
        ...
