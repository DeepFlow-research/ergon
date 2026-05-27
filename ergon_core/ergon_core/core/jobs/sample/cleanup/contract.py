from uuid import UUID

from ergon_core.core.application.events.runtime import SampleCancelledEvent, SampleCleanupEvent
from pydantic import BaseModel


class SampleCleanupResult(BaseModel):
    model_config = {"frozen": True}

    sample_id: UUID
    status: str | None = None
    sandbox_terminated: bool = False
    sandbox_id: str | None = None
    error: str | None = None
