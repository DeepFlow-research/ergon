from typing import ClassVar
from uuid import UUID

from ergon_core.core.application.events.base import InngestEventContract
from pydantic import BaseModel


class RunCancelledEvent(InngestEventContract):
    name: ClassVar[str] = "run/cancelled"

    run_id: UUID


class RunCleanupEvent(InngestEventContract):
    name: ClassVar[str] = "run/cleanup"

    run_id: UUID
    status: str
    error_message: str | None = None


class RunCleanupResult(BaseModel):
    model_config = {"frozen": True}

    run_id: UUID
    status: str | None = None
    sandbox_terminated: bool = False
    sandbox_id: str | None = None
    error: str | None = None
