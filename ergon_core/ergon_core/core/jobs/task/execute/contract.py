from uuid import UUID

from ergon_core.core.application.events.runtime import TaskReadyEvent, TaskStartedEvent
from pydantic import BaseModel


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
