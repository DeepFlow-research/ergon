"""Custom non-retryable Inngest errors for Arcane runtime.

Every exception auto-logs at ERROR level on construction so failures
are always visible in stdout regardless of how the caller handles them.
"""

from h_arcane.core.runtime.errors.inngest_errors import (
    ArcaneNonRetriableError,
    ConfigurationError,
    ContractViolationError,
    DataIntegrityError,
    RegistryLookupError,
)

__all__ = [
    "ArcaneNonRetriableError",
    "ConfigurationError",
    "ContractViolationError",
    "DataIntegrityError",
    "RegistryLookupError",
]
