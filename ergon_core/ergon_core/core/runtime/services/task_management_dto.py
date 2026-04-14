"""DTOs for TaskManagementService — dynamic delegation commands and results."""

from uuid import UUID

from pydantic import BaseModel, Field


class AddTaskCommand(BaseModel):
    """Command to spawn a new sub-task from a running worker."""

    model_config = {"frozen": True}

    run_id: UUID
    definition_id: UUID
    parent_node_id: UUID
    description: str
    worker_binding_key: str
    task_payload: dict[str, object] = Field(default_factory=dict)


class AddTaskResult(BaseModel):
    """Result of spawning a new sub-task."""

    model_config = {"frozen": True}

    node_id: UUID
    edge_id: UUID
    task_key: str
    status: str


class AbandonTaskCommand(BaseModel):
    """Command to abandon a stalling sub-task."""

    model_config = {"frozen": True}

    run_id: UUID
    node_id: UUID


class AbandonTaskResult(BaseModel):
    model_config = {"frozen": True}

    node_id: UUID
    previous_status: str
    new_status: str


class RefineTaskCommand(BaseModel):
    """Command to update description on a pending sub-task."""

    model_config = {"frozen": True}

    run_id: UUID
    node_id: UUID
    new_description: str


class RefineTaskResult(BaseModel):
    model_config = {"frozen": True}

    node_id: UUID
    old_description: str
    new_description: str
