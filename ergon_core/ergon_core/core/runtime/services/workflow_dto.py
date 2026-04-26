from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class WorkflowTaskRef(BaseModel):
    model_config = {"frozen": True}

    node_id: UUID
    task_slug: str
    status: str
    level: int
    parent_node_id: UUID | None = None
    assigned_worker_slug: str | None = None


class WorkflowExecutionRef(BaseModel):
    model_config = {"frozen": True}

    execution_id: UUID
    status: str
    attempt_number: int
    final_assistant_message: str | None = None


class WorkflowResourceRef(BaseModel):
    model_config = {"frozen": True}

    resource_id: UUID
    run_id: UUID
    task_execution_id: UUID | None
    node_id: UUID | None
    task_slug: str | None
    kind: str
    name: str
    mime_type: str
    size_bytes: int
    file_path: str
    content_hash: str | None = None
    copied_from_resource_id: UUID | None = None
    created_at: datetime


class WorkflowDependencyRef(BaseModel):
    model_config = {"frozen": True}

    edge_id: UUID
    edge_status: str
    source: WorkflowTaskRef
    target: WorkflowTaskRef


class WorkflowBlockerRef(BaseModel):
    model_config = {"frozen": True}

    task: WorkflowTaskRef
    reason: str
    details: list[str] = Field(default_factory=list)
    suggested_commands: list[str] = Field(default_factory=list)


class WorkflowNextActionRef(BaseModel):
    model_config = {"frozen": True}

    priority: str
    task: WorkflowTaskRef | None = None
    summary: str
    suggested_commands: list[str] = Field(default_factory=list)


class WorkflowMaterializedResourceRef(BaseModel):
    model_config = {"frozen": True}

    source_resource_id: UUID
    copied_resource_id: UUID | None
    copied_from_resource_id: UUID
    source_name: str
    copied_name: str
    source_content_hash: str | None
    copied_content_hash: str | None
    sandbox_path: str
    dry_run: bool = False
    source_mutated: bool = False
