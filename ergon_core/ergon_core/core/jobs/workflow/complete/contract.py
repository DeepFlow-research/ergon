from typing import Literal
from uuid import UUID

from ergon_core.core.application.events.runtime import WorkflowCompletedEvent
from pydantic import BaseModel


class WorkflowCompleteResult(BaseModel):
    model_config = {"frozen": True}

    sample_id: UUID
    status: Literal["completed"] = "completed"
    final_score: float | None = None
    normalized_score: float | None = None
    evaluators_count: int = 0
