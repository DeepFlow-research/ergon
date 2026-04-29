"""Non-retryable Inngest errors for the Ergon runtime."""

import logging
from uuid import UUID

import inngest

logger = logging.getLogger("ergon.infrastructure.inngest")

NonRetriableError = inngest.NonRetriableError


class ErgonNonRetriableError(inngest.NonRetriableError):
    """Base for all Ergon non-retryable errors. Logs on construction."""

    def __init__(self, message: str, **context: object) -> None:
        ctx_str = " ".join(f"{k}={v}" for k, v in context.items()) if context else ""
        full = f"{message} {ctx_str}".strip()
        logger.error("[%s] %s", type(self).__name__, full)
        super().__init__(message=full)


class RegistryLookupError(ErgonNonRetriableError):
    """A slug was not found in the builtins registry."""

    def __init__(self, registry_name: str, slug: str, **context: object) -> None:
        super().__init__(
            f"{registry_name} registry has no entry for {slug!r}",
            **context,
        )


class DataIntegrityError(ErgonNonRetriableError):
    """A required DB row is missing or corrupt."""

    def __init__(self, entity: str, entity_id: UUID | str, **context: object) -> None:
        super().__init__(
            f"{entity} {entity_id} not found",
            **context,
        )


class ConfigurationError(ErgonNonRetriableError):
    """An experiment definition has invalid or missing configuration."""

    def __init__(self, detail: str, **context: object) -> None:
        super().__init__(detail, **context)


class ContractViolationError(ErgonNonRetriableError):
    """A runtime contract or invariant was broken."""

    def __init__(self, detail: str, **context: object) -> None:
        super().__init__(detail, **context)
