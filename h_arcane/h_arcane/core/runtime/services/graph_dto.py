"""DTOs for WorkflowGraphRepository return types.

Frozen Pydantic models. Callers never receive raw SQLModel rows.
"""

from typing import Any
from uuid import UUID

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
    target_type: str
    target_id: UUID
    namespace: str
    sequence: int
    payload: dict[str, Any]


class GraphMutationDto(BaseModel):
    model_config = {"frozen": True}

    id: UUID
    run_id: UUID
    sequence: int
    mutation_type: str
    target_type: str
    target_id: UUID
    actor: str
    old_value: dict[str, Any] | None
    new_value: dict[str, Any]
    reason: str | None


class WorkflowGraphDto(BaseModel):
    """Full graph snapshot returned by get_graph()."""

    model_config = {"frozen": True}

    run_id: UUID
    nodes: list[GraphNodeDto] = Field(default_factory=list)
    edges: list[GraphEdgeDto] = Field(default_factory=list)
