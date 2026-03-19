"""Provider exception hierarchy for CivPulse geo-api.

All provider errors are subclasses of ProviderError, enabling callers to catch
the base class for generic handling or specific subclasses for typed retry logic.

Hierarchy:
    ProviderError (base)
    ├── ProviderNetworkError   — provider unreachable, connection refused, timeout
    ├── ProviderAuthError      — bad API key, expired token, permission denied
    └── ProviderRateLimitError — rate limit exceeded, quota exhausted
"""


class ProviderError(Exception):
    """Base exception for all provider errors.

    Catch this for generic provider failure handling.
    Catch subtypes for typed retry/fallback logic.
    """
    pass


class ProviderNetworkError(ProviderError):
    """Raised when a provider is unreachable or returns a network error.

    Examples: connection refused, timeout, DNS resolution failure,
    provider returning 5xx with no useful body.
    """
    pass


class ProviderAuthError(ProviderError):
    """Raised when provider authentication fails.

    Examples: invalid API key, expired OAuth token, IP not allowlisted,
    account suspended.
    """
    pass


class ProviderRateLimitError(ProviderError):
    """Raised when a provider returns a rate limit or quota response.

    Examples: 429 Too Many Requests, daily quota exhausted,
    per-second rate exceeded.
    """
    pass
