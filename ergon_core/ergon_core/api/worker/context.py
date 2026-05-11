"""Per-execution runtime state passed to Worker.execute()."""

from uuid import UUID

from pydantic import BaseModel, Field
from ergon_core.core.shared.json_types import JsonObject


class WorkerContext(BaseModel):
    """Runtime context for a single worker execution."""

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
    ) #TODO: find some way to remove this, seems like a bad dependency
    execution_id: UUID
    sandbox_id: str
    task_id: UUID
    node_id: UUID | None = Field(
        default=None,
        description="RunGraphNode.id — this worker's graph node identity.",
    )
    metadata: JsonObject = Field(default_factory=dict)
