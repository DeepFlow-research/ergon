from typing import ClassVar
from uuid import UUID

from ergon_core.core.application.events.base import InngestEventContract
from pydantic import BaseModel


class TaskReadyEvent(InngestEventContract):
    name: ClassVar[str] = "task/ready"

    run_id: UUID
    definition_id: UUID
    task_id: UUID


class TaskStartedEvent(InngestEventContract):
    name: ClassVar[str] = "task/started"

    run_id: UUID
    definition_id: UUID
    task_id: UUID
    execution_id: UUID


class TaskExecuteResult(BaseModel):
    model_config = {"frozen": True}

    run_id: UUID
    task_id: UUID
    execution_id: UUID
    success: bool = False
    skipped: bool = False
    skip_reason: str | None = None
    outputs_count: int = 0
    error: str | None = None
