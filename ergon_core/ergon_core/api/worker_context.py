"""Per-execution runtime state passed to Worker.execute()."""

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class WorkerContext(BaseModel):
    """Runtime context for a single worker execution.

    Contains only per-execution state that the worker cannot know at
    construction time.  Tools and configuration belong on the Worker itself.
    """

    model_config = {"frozen": True}

    run_id: UUID
    definition_id: UUID | None = Field(
        default=None,
        description=(
            "ExperimentDefinition.id — the experiment template that governs "
            "this run's worker bindings, evaluator bindings, and benchmark "
            "config. Used by delegation tools to resolve assigned_worker_slug "
            "to worker_type."
        ),
    )
    task_id: UUID
    execution_id: UUID
    sandbox_id: str
    node_id: UUID | None = Field(
        default=None,
        description="RunGraphNode.id — this worker's graph node identity.",
    )
    metadata: dict[str, Any] = Field(default_factory=dict)  # slopcop: ignore[no-typing-any]
