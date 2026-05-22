from uuid import UUID

from ergon_core.core.application.events.runtime import RunCancelledEvent, RunCleanupEvent
from pydantic import BaseModel


class RunCleanupResult(BaseModel):
    model_config = {"frozen": True}

    run_id: UUID
    status: str | None = None
    sandbox_terminated: bool = False
    sandbox_id: str | None = None
    error: str | None = None
