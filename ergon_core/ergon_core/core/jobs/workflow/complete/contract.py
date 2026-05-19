from typing import ClassVar, Literal
from uuid import UUID

from ergon_core.core.application.events.base import InngestEventContract
from pydantic import BaseModel


class WorkflowCompletedEvent(InngestEventContract):
    name: ClassVar[str] = "workflow/completed"

    run_id: UUID
    definition_id: UUID


class WorkflowCompleteResult(BaseModel):
    model_config = {"frozen": True}

    run_id: UUID
    status: Literal["completed"] = "completed"
    final_score: float | None = None
    normalized_score: float | None = None
    evaluators_count: int = 0
