"""Conventional status values for RunGraphNode.

The graph layer accepts any string -- these are not enforced by the
schema. They are the values used by the core runtime, propagation,
and dynamic delegation logic. Experiment layers may add domain-
specific statuses without changing core code.
"""

PENDING = "pending"
RUNNING = "running"
COMPLETED = "completed"
FAILED = "failed"
ABANDONED = "abandoned"

TERMINAL_STATUSES = frozenset({COMPLETED, FAILED, ABANDONED})
