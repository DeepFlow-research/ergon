from uuid import UUID

from ergon_core.core.application.events.runtime import SampleStartedEvent
from pydantic import BaseModel


class WorkflowStartResult(BaseModel):
    model_config = {"frozen": True}

    sample_id: UUID
    initial_ready_tasks: int = 0
    total_tasks: int = 0
