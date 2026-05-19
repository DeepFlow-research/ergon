from uuid import UUID

from ergon_core.core.application.events.runtime import WorkflowStartedEvent
from pydantic import BaseModel


class WorkflowStartResult(BaseModel):
    model_config = {"frozen": True}

    run_id: UUID
    initial_ready_tasks: int = 0
    total_tasks: int = 0
