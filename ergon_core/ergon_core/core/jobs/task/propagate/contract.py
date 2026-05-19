from typing import ClassVar
from uuid import UUID

from ergon_core.core.application.events.base import InngestEventContract
from pydantic import BaseModel


class TaskCompletedEvent(InngestEventContract):
    name: ClassVar[str] = "task/completed"

    run_id: UUID
    definition_id: UUID
    task_id: UUID
    execution_id: UUID
    sandbox_id: str


class TaskFailedEvent(InngestEventContract):
    name: ClassVar[str] = "task/failed"

    run_id: UUID
    definition_id: UUID
    task_id: UUID
    execution_id: UUID
    error: str
    sandbox_id: str | None = None


class TaskPropagateResult(BaseModel):
    model_config = {"frozen": True}

    run_id: UUID
    task_id: UUID
    newly_ready_tasks: int = 0
    workflow_complete: bool = False
    workflow_failed: bool = False
