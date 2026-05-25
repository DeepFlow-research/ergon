"""DTOs for RuntimeGraphRepository return types.

Frozen Pydantic models. Callers never receive raw SQLModel rows.

UUID fields use NewType aliases (SampleId, NodeId, etc.) so that type
checkers catch cross-field swaps — e.g. passing a task id where a
sample_id is expected. The aliases are erased at runtime (zero
serialization cost).
"""

from uuid import UUID

from ergon_core.api.benchmark import Task
from ergon_core.core.application.runtime.status import NodeStatus
from ergon_core.core.persistence.shared.types import (
    DefinitionId,
    EdgeId,
    NodeId,
    SampleId,
)
from pydantic import BaseModel, Field

# TODO: this file def needs a deduplication pass vs other DTOs and schemas in different modules / files


class MutationMeta(BaseModel):
    """Audit context for every graph mutation.

    ``actor`` is for audit logging (who did this), not authorization
    (were they allowed to). The experiment layer enforces permissions
    before calling the repository; the repository just records the actor.
    """

    model_config = {"frozen": True}

    actor: str
    reason: str | None = None


class GraphNodeDto(BaseModel):
    model_config = {"frozen": True}

    task_id: NodeId
    sample_id: SampleId
    instance_key: str
    task_slug: str
    description: str
    status: str = Field(
        description=(
            "Domain-specific node lifecycle status stored as a string because the database "
            "allows experiment-specific statuses; see application/runtime/status.py."
        )
    )
    assigned_worker_slug: str | None
    parent_task_id: NodeId | None
    level: int


class GraphTaskRef(BaseModel):
    """Lightweight task-node reference for workflow/tool projections."""

    model_config = {"frozen": True}

    task_id: NodeId
    task_slug: str
    status: NodeStatus
    level: int
    parent_task_id: NodeId | None = None
    assigned_worker_slug: str | None = None
    description: str | None = None


class GraphEdgeDto(BaseModel):
    model_config = {"frozen": True}

    id: EdgeId
    sample_id: SampleId
    definition_dependency_id: DefinitionId | None
    source_task_id: NodeId
    target_task_id: NodeId
    status: str = Field(
        description=(
            "Domain-specific edge lifecycle status stored as a string because the database "
            "allows experiment-specific dependency statuses."
        )
    )


class WorkflowGraphDto(BaseModel):
    """Full graph snapshot returned by get_graph()."""

    model_config = {"frozen": True}

    sample_id: SampleId
    nodes: list[GraphNodeDto] = Field(default_factory=list)
    edges: list[GraphEdgeDto] = Field(default_factory=list)


class SampleGraphNodeView(BaseModel):
    """Typed view of one ``sample_graph_nodes`` row + its inflated Task.

    The job body receives this view from ``RuntimeGraphRepository.node``
    instead of raw JSON. The Task is already inflated via
    ``Task.from_definition`` so callers downstream of the repo never see
    ``dict[str, Any]``.

    ``task_id`` is the runtime identity. Static definition ids are not
    part of the runtime identity.
    """

    model_config = {"frozen": True, "arbitrary_types_allowed": True}

    sample_id: SampleId
    task_id: UUID
    parent_task_id: NodeId | None
    status: str
    task: Task
    is_dynamic: bool = False
