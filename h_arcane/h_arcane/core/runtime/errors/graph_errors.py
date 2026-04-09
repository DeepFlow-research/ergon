"""Graph repository errors.

Deliberately NOT Inngest-specific (no NonRetriableError subclass).
The graph layer must stay independent of the execution runtime so it
can be reused in training pipelines, replay systems, and test harnesses
that don't run inside Inngest. The Inngest layer wraps these into
NonRetriableError at the function boundary if needed.
"""

import logging
from typing import Any
from uuid import UUID

logger = logging.getLogger("arcane.graph")


class GraphError(Exception):
    """Base for all graph repository errors."""

    def __init__(self, message: str, **context: Any) -> None:  # slopcop: ignore[no-typing-any]
        ctx_str = " ".join(f"{k}={v}" for k, v in context.items()) if context else ""
        full = f"{message} {ctx_str}".strip()
        logger.error("[%s] %s", type(self).__name__, full)
        super().__init__(full)


class CycleError(GraphError):
    """Adding the proposed edge would create a cycle."""

    def __init__(self, source_id: UUID, target_id: UUID, **context: Any) -> None:  # slopcop: ignore[no-typing-any]
        super().__init__(
            f"Edge {source_id} -> {target_id} would create a cycle",
            **context,
        )


class NodeNotFoundError(GraphError):
    """Referenced node does not exist in this run's graph."""

    def __init__(self, node_id: UUID, **context: Any) -> None:  # slopcop: ignore[no-typing-any]
        super().__init__(f"Node {node_id} not found", **context)


class EdgeNotFoundError(GraphError):
    """Referenced edge does not exist in this run's graph."""

    def __init__(self, edge_id: UUID, **context: Any) -> None:  # slopcop: ignore[no-typing-any]
        super().__init__(f"Edge {edge_id} not found", **context)


class AnnotationNotFoundError(GraphError):
    """Referenced annotation does not exist."""

    def __init__(
        self, target_type: str, target_id: UUID, namespace: str, **context: Any  # slopcop: ignore[no-typing-any]
    ) -> None:
        super().__init__(
            f"Annotation {namespace!r} on {target_type} {target_id} not found",
            **context,
        )


class DanglingEdgeError(GraphError):
    """Edge references a node that does not exist."""

    def __init__(self, edge_id: UUID, missing_node_id: UUID, **context: Any) -> None:  # slopcop: ignore[no-typing-any]
        super().__init__(
            f"Edge {edge_id} references missing node {missing_node_id}",
            **context,
        )
