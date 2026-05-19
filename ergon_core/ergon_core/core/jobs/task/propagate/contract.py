from uuid import UUID

from ergon_core.core.application.events.runtime import TaskCompletedEvent, TaskFailedEvent
from pydantic import BaseModel


class TaskPropagateResult(BaseModel):
    model_config = {"frozen": True}

    run_id: UUID
    task_id: UUID
    newly_ready_tasks: int = 0
    workflow_complete: bool = False
    workflow_failed: bool = False
