"""Non-retryable Inngest errors for the Ergon runtime.

Each subclass represents a distinct failure category. All auto-log at
ERROR level on construction so the failure is always visible in stdout,
even if the caller swallows or re-wraps the exception.

Usage:
    raise RegistryLookupError("worker", "react-v1")
    raise DataIntegrityError("RunRecord", run_id)
    raise ConfigurationError("worker_type is not set for task", task_id=task_id)
    raise ContractViolationError("sandbox-setup returned dict, expected SandboxReadyResult")
"""

import logging
from uuid import UUID

import inngest

logger = logging.getLogger("ergon.runtime.errors")


class ErgonNonRetriableError(inngest.NonRetriableError):
    """Base for all Ergon non-retryable errors. Logs on construction."""

    def __init__(self, message: str, **context: object) -> None:
        ctx_str = " ".join(f"{k}={v}" for k, v in context.items()) if context else ""
        full = f"{message} {ctx_str}".strip()
        logger.error("[%s] %s", type(self).__name__, full)
        super().__init__(message=full)


class RegistryLookupError(ErgonNonRetriableError):
    """A slug was not found in the builtins registry.

    This is a definition-level problem: the experiment references a
    benchmark/worker/evaluator/sandbox-manager that is not registered.
    Retrying will always produce the same miss.
    """

    def __init__(self, registry_name: str, slug: str, **context: object) -> None:
        super().__init__(
            f"{registry_name} registry has no entry for {slug!r}",
            **context,
        )


class DataIntegrityError(ErgonNonRetriableError):
    """A required DB row is missing or corrupt.

    The row should have been created by a prior step in the pipeline.
    Its absence indicates a data integrity violation that will not
    self-heal on retry.
    """

    def __init__(self, entity: str, entity_id: UUID | str, **context: object) -> None:
        super().__init__(
            f"{entity} {entity_id} not found",
            **context,
        )


class ConfigurationError(ErgonNonRetriableError):
    """An experiment definition has invalid or missing configuration.

    Examples: worker_type not set on a task assignment, unknown status
    string in an event payload.
    """

    def __init__(self, detail: str, **context: object) -> None:
        super().__init__(detail, **context)


class ContractViolationError(ErgonNonRetriableError):
    """A runtime contract or invariant was broken.

    Examples: an Inngest step returned an unexpected type, a spec/result
    index mismatch, or an unreachable code path was reached.
    """

    def __init__(self, detail: str, **context: object) -> None:
        super().__init__(detail, **context)
