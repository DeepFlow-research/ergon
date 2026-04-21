"""Shared type aliases for stringly-typed identifiers.

NewType aliases are erased at runtime but catch cross-field
misassignment in type checkers (e.g., passing a task_slug where a
node_id is expected).
"""

from typing import NewType
from uuid import UUID

# ── String aliases ────────────────────────────────────────────────
TaskSlug = NewType("TaskSlug", str)
AssignedWorkerSlug = NewType("AssignedWorkerSlug", str)
BenchmarkSlug = NewType("BenchmarkSlug", str)

# ── UUID aliases ──────────────────────────────────────────────────
RunId = NewType("RunId", UUID)
NodeId = NewType("NodeId", UUID)
DefinitionId = NewType("DefinitionId", UUID)
ExecutionId = NewType("ExecutionId", UUID)
EdgeId = NewType("EdgeId", UUID)
