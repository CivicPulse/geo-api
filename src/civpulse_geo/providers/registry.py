"""Provider registry with eager instantiation.

load_providers() is called at application startup (from FastAPI lifespan).
By eagerly instantiating all configured provider classes, ABC enforcement
fires at startup — any class that omits a required abstract method raises
TypeError before the first HTTP request is served.

This satisfies INFRA-02: 'a concrete class that omits a required abstract
method raises an error at load time.'
"""
from loguru import logger

from civpulse_geo.providers.base import GeocodingProvider, ValidationProvider


def load_providers(
    provider_classes: dict[str, type],
) -> dict[str, GeocodingProvider | ValidationProvider]:
    """Eagerly instantiate all configured providers.

    Iterates over the provider_classes dict, instantiates each class, and
    stores the instance in the registry. If any class is missing a required
    abstract method, Python's ABC machinery raises TypeError here at startup —
    not on first call.

    Args:
        provider_classes: Mapping of registry name to provider class.
            Example: {"census": CensusGeocodingProvider, "usps": USPSValidationProvider}

    Returns:
        Dict mapping registry name to instantiated provider.
        Empty dict if provider_classes is empty.

    Raises:
        TypeError: If any provider class is missing required abstract methods.
            This is intentional — surfaces configuration errors at startup.
    """
    registry: dict[str, GeocodingProvider | ValidationProvider] = {}

    for name, cls in provider_classes.items():
        logger.info(f"Loading provider: {name} ({cls.__name__})")
        # ABC enforcement fires here — TypeError if any abstract method is missing
        instance = cls()
        registry[name] = instance
        logger.info(f"Provider loaded: {name}")

    return registry
