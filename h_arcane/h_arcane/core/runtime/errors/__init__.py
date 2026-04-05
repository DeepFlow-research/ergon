"""Custom errors for Arcane runtime.

Inngest errors auto-log at ERROR level on construction so failures
are always visible in stdout regardless of how the caller handles them.

Graph errors are runtime-agnostic (no Inngest dependency).
"""

from h_arcane.core.runtime.errors.graph_errors import (
    AnnotationNotFoundError,
    CycleError,
    DanglingEdgeError,
    EdgeNotFoundError,
    GraphError,
    NodeNotFoundError,
)
from h_arcane.core.runtime.errors.inngest_errors import (
    ArcaneNonRetriableError,
    ConfigurationError,
    ContractViolationError,
    DataIntegrityError,
    RegistryLookupError,
)

__all__ = [
    "ArcaneNonRetriableError",
    "AnnotationNotFoundError",
    "ConfigurationError",
    "ContractViolationError",
    "CycleError",
    "DanglingEdgeError",
    "DataIntegrityError",
    "EdgeNotFoundError",
    "GraphError",
    "NodeNotFoundError",
    "RegistryLookupError",
]
