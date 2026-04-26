"""Custom errors for Ergon runtime.

Inngest errors auto-log at ERROR level on construction so failures
are always visible in stdout regardless of how the caller handles them.

Graph errors are runtime-agnostic (no Inngest dependency).
"""

from ergon_core.core.runtime.errors.delegation_errors import (
    DelegationError,
    TaskAlreadyTerminalError,
)
from ergon_core.core.runtime.errors.graph_errors import (
    CycleError,
    DanglingEdgeError,
    EdgeNotFoundError,
    GraphError,
    NodeNotFoundError,
)
from ergon_core.core.runtime.errors.inngest_errors import (
    ConfigurationError,
    ContractViolationError,
    DataIntegrityError,
    ErgonNonRetriableError,
    RegistryLookupError,
)

__all__ = [
    "DelegationError",
    "ErgonNonRetriableError",
    "ConfigurationError",
    "ContractViolationError",
    "CycleError",
    "DanglingEdgeError",
    "DataIntegrityError",
    "EdgeNotFoundError",
    "GraphError",
    "NodeNotFoundError",
    "RegistryLookupError",
    "TaskAlreadyTerminalError",
]
