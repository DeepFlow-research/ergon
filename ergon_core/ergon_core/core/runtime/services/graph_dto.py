"""DTOs for WorkflowGraphRepository return types.

Frozen Pydantic models. Callers never receive raw SQLModel rows.
"""

from typing import Annotated, Literal
from uuid import UUID

from ergon_core.core.persistence.graph.models import GraphTargetType, MutationType
from pydantic import BaseModel, Field


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

    id: UUID
    run_id: UUID
    definition_task_id: UUID | None
    instance_key: str
    task_key: str
    description: str
    status: str
    assigned_worker_key: str | None


class GraphEdgeDto(BaseModel):
    model_config = {"frozen": True}

    id: UUID
    run_id: UUID
    definition_dependency_id: UUID | None
    source_node_id: UUID
    target_node_id: UUID
    status: str


class GraphAnnotationDto(BaseModel):
    model_config = {"frozen": True}

    id: UUID
    run_id: UUID
    target_type: GraphTargetType
    target_id: UUID
    namespace: str
    sequence: int
    payload: dict[str, object]


class GraphMutationDto(BaseModel):
    model_config = {"frozen": True}

    id: UUID
    run_id: UUID
    sequence: int
    mutation_type: MutationType
    target_type: GraphTargetType
    target_id: UUID
    actor: str
    old_value: "GraphMutationValue | None"
    new_value: "GraphMutationValue"
    reason: str | None


class WorkflowGraphDto(BaseModel):
    """Full graph snapshot returned by get_graph()."""

    model_config = {"frozen": True}

    run_id: UUID
    nodes: list[GraphNodeDto] = Field(default_factory=list)
    edges: list[GraphEdgeDto] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Typed mutation value models (discriminated union on mutation_type)
# ---------------------------------------------------------------------------


class NodeAddedMutation(BaseModel):
    """node.added — full node snapshot."""

    model_config = {"frozen": True}

    mutation_type: Literal["node.added"] = "node.added"
    task_key: str
    instance_key: str
    description: str
    status: str
    assigned_worker_key: str | None


class NodeRemovedMutation(BaseModel):
    """node.removed — node snapshot at removal time."""

    model_config = {"frozen": True}

    mutation_type: Literal["node.removed"] = "node.removed"
    task_key: str
    instance_key: str
    description: str
    status: str
    assigned_worker_key: str | None


class NodeStatusChangedMutation(BaseModel):
    """node.status_changed."""

    model_config = {"frozen": True}

    mutation_type: Literal["node.status_changed"] = "node.status_changed"
    status: str


class NodeFieldChangedMutation(BaseModel):
    """node.field_changed."""

    model_config = {"frozen": True}

    mutation_type: Literal["node.field_changed"] = "node.field_changed"
    field: Literal["description", "assigned_worker_key"]
    value: str | None


class EdgeAddedMutation(BaseModel):
    """edge.added — full edge snapshot."""

    model_config = {"frozen": True}

    mutation_type: Literal["edge.added"] = "edge.added"
    source_node_id: str
    target_node_id: str
    status: str


class EdgeRemovedMutation(BaseModel):
    """edge.removed."""

    model_config = {"frozen": True}

    mutation_type: Literal["edge.removed"] = "edge.removed"
    source_node_id: str
    target_node_id: str
    status: str


class EdgeStatusChangedMutation(BaseModel):
    """edge.status_changed."""

    model_config = {"frozen": True}

    mutation_type: Literal["edge.status_changed"] = "edge.status_changed"
    status: str


class AnnotationSetMutation(BaseModel):
    """annotation.set."""

    model_config = {"frozen": True}

    mutation_type: Literal["annotation.set"] = "annotation.set"
    namespace: str
    payload: dict[str, object]


class AnnotationDeletedMutation(BaseModel):
    """annotation.deleted — tombstone."""

    model_config = {"frozen": True}

    mutation_type: Literal["annotation.deleted"] = "annotation.deleted"
    namespace: str
    payload: dict[str, object]


GraphMutationValue = Annotated[
    NodeAddedMutation
    | NodeRemovedMutation
    | NodeStatusChangedMutation
    | NodeFieldChangedMutation
    | EdgeAddedMutation
    | EdgeRemovedMutation
    | EdgeStatusChangedMutation
    | AnnotationSetMutation
    | AnnotationDeletedMutation,
    Field(discriminator="mutation_type"),
]
