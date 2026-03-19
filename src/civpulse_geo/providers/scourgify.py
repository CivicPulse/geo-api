"""Scourgify-based validation provider for USPS Pub 28 address normalization.

Uses the scourgify library for offline address normalization. No external API calls.
scourgify is synchronous pure-Python with no I/O, so calling from async is safe
(no asyncio.to_thread() needed).

Key behaviors:
- Normalizes street type abbreviations: "Road" -> "RD", "Street" -> "ST"
- Normalizes state names: "Georgia" -> "GA"
- Extracts secondary designators to address_line_2: "APT 4B", "STE 200"
- Preserves ZIP+4 in postal_code: "31201-5678" remains "31201-5678"
- confidence is always 1.0 on success (binary: parse or fail)
- delivery_point_verified is always False (offline normalization only)
- Raises ProviderError for PO Boxes and unparseable addresses
"""
from scourgify import normalize_address_record
from scourgify.exceptions import (
    UnParseableAddressError,
    AmbiguousAddressError,
    AddressNormalizationError,
    IncompleteAddressError,
)

from civpulse_geo.providers.base import ValidationProvider
from civpulse_geo.providers.exceptions import ProviderError
from civpulse_geo.providers.schemas import ValidationResult

SCOURGIFY_CONFIDENCE = 1.0


class ScourgifyValidationProvider(ValidationProvider):
    """Validation provider using scourgify for USPS Pub 28 normalization.

    Scourgify is binary: either it parses successfully (confidence=1.0) or raises
    an exception (unparseable). There are no partial matches.

    delivery_point_verified is always False — scourgify cannot confirm mail delivery.
    For DPV confirmation, a USPS v3 API or Lob/SmartyStreets adapter is required.

    Design notes:
    - scourgify has no I/O (pure offline logic) so async wrapping is not needed
    - normalize_address_record returns dict with keys:
        address_line_1, address_line_2, city, state, postal_code
    - address_line_2 is the secondary designator extracted by scourgify
    """

    @property
    def provider_name(self) -> str:
        """Unique string identifier for this provider."""
        return "scourgify"

    async def validate(self, address: str) -> ValidationResult:
        """Validate and normalize a single freeform US address.

        Args:
            address: Freeform address string (e.g. "123 Main Road, Macon, Georgia 31201").

        Returns:
            ValidationResult with USPS Pub 28 normalized components.

        Raises:
            ProviderError: Address is unparseable (PO Box, gibberish, incomplete).
        """
        try:
            parsed = normalize_address_record(address)
        except (
            UnParseableAddressError,
            AmbiguousAddressError,
            AddressNormalizationError,
            IncompleteAddressError,
        ) as e:
            raise ProviderError(f"Address unparseable by scourgify: {e}") from e

        address_line_1 = (parsed.get("address_line_1") or "").strip()
        address_line_2 = (parsed.get("address_line_2") or "").strip() or None
        city = (parsed.get("city") or "").strip() or None
        state = (parsed.get("state") or "").strip() or None
        postal_code = (parsed.get("postal_code") or "").strip() or None

        # Build full normalized address string from non-None components
        parts = [p for p in [address_line_1, address_line_2, city, state, postal_code] if p]
        normalized_address = " ".join(parts) if parts else address_line_1

        return ValidationResult(
            normalized_address=normalized_address,
            address_line_1=address_line_1,
            address_line_2=address_line_2,
            city=city,
            state=state,
            postal_code=postal_code,
            confidence=SCOURGIFY_CONFIDENCE,
            delivery_point_verified=False,
            provider_name=self.provider_name,
            original_input=address,
        )

    async def batch_validate(self, addresses: list[str]) -> list[ValidationResult]:
        """Validate a list of freeform addresses.

        Processes addresses serially. scourgify is synchronous and CPU-bound,
        so no concurrent benefit from asyncio.gather() here.

        Args:
            addresses: List of freeform address strings.

        Returns:
            List of ValidationResult in the same order as input.

        Raises:
            ProviderError: If any address is unparseable.
        """
        results = []
        for addr in addresses:
            result = await self.validate(addr)
            results.append(result)
        return results
