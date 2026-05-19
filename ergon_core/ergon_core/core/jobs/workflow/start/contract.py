from typing import ClassVar
from uuid import UUID

from ergon_core.core.application.events.base import InngestEventContract
from pydantic import BaseModel


class WorkflowStartedEvent(InngestEventContract):
    name: ClassVar[str] = "workflow/started"

    run_id: UUID
    definition_id: UUID


class WorkflowStartResult(BaseModel):
    model_config = {"frozen": True}

    run_id: UUID
    initial_ready_tasks: int = 0
    total_tasks: int = 0
