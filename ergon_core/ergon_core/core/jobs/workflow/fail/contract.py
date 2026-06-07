from typing import Literal
from uuid import UUID

from ergon_core.core.application.events.runtime import WorkflowFailedEvent
from pydantic import BaseModel


class WorkflowFailedResult(BaseModel):
    model_config = {"frozen": True}

    sample_id: UUID
    status: Literal["failed"] = "failed"
    error: str | None = None
