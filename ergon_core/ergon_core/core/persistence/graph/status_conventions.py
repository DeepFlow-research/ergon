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
ABANDONED = "abandoned"

TERMINAL_STATUSES = frozenset({COMPLETED, FAILED, ABANDONED})

NodeStatus = Literal["pending", "ready", "running", "completed", "failed", "abandoned"]

# ── Edge status ───────────────────────────────────────────────────
EDGE_PENDING = "pending"
EDGE_SATISFIED = "satisfied"
EDGE_ACTIVE = "active"
EDGE_ABANDONED = "abandoned"

EdgeStatus = Literal["pending", "satisfied", "active", "abandoned"]
