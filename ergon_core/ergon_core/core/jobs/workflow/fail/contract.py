from typing import ClassVar, Literal
from uuid import UUID

from ergon_core.core.application.events.base import InngestEventContract
from pydantic import BaseModel


class WorkflowFailedEvent(InngestEventContract):
    name: ClassVar[str] = "workflow/failed"

    run_id: UUID
    definition_id: UUID
    error: str


class WorkflowFailedResult(BaseModel):
    model_config = {"frozen": True}

    run_id: UUID
    status: Literal["failed"] = "failed"
    error: str | None = None
