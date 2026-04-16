"""Shared type aliases for stringly-typed identifiers.

NewType aliases are erased at runtime but catch cross-field
misassignment in type checkers (e.g., passing a benchmark slug
where a worker binding key is expected, or a node_id where a
run_id is expected).
"""

from typing import NewType
from uuid import UUID

# ── String aliases ────────────────────────────────────────────────
WorkerBindingKey = NewType("WorkerBindingKey", str)
BenchmarkSlug = NewType("BenchmarkSlug", str)

# ── UUID aliases ──────────────────────────────────────────────────
# Erased at runtime (zero Pydantic/serialization cost).
# Catch cross-field UUID swaps at type-check time (ty / mypy).
RunId = NewType("RunId", UUID)
NodeId = NewType("NodeId", UUID)
DefinitionId = NewType("DefinitionId", UUID)
ExecutionId = NewType("ExecutionId", UUID)
EdgeId = NewType("EdgeId", UUID)
