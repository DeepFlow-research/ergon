"""Conventional status values for RunGraphNode and RunGraphEdge.

The graph layer accepts any string at the DB level -- these are not
enforced by the schema. They are the values used by the core runtime,
propagation, and dynamic delegation logic. Experiment layers may add
domain-specific statuses without changing core code.

The Literal type aliases below are for use in service signatures, DTOs,
and function annotations. They catch typos at type-check time without
constraining the DB column.
"""

from typing import Literal

# ── Node status ───────────────────────────────────────────────────
PENDING = "pending"
READY = "ready"
RUNNING = "running"
COMPLETED = "completed"
FAILED = "failed"
CANCELLED = "cancelled"
BLOCKED = "blocked"

TERMINAL_STATUSES = frozenset({COMPLETED, FAILED, CANCELLED})
NON_AUTONOMOUS_STATUSES = TERMINAL_STATUSES | frozenset({BLOCKED})

NodeStatus = Literal["pending", "ready", "running", "completed", "failed", "cancelled", "blocked"]


def is_terminal_node_status(status: str) -> bool:
    return status in TERMINAL_STATUSES


def is_blockable_node_status(status: str) -> bool:
    return status != RUNNING and status not in TERMINAL_STATUSES

# ── Edge status ───────────────────────────────────────────────────
# Edges are pure dependency relations (containment lives on the node).
# "active" is removed — delegation edges no longer exist.
EDGE_PENDING = "pending"
EDGE_SATISFIED = "satisfied"
EDGE_INVALIDATED = "invalidated"

EdgeStatus = Literal["pending", "satisfied", "invalidated"]
