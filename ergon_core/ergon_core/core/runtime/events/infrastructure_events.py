"""Infrastructure lifecycle event contracts."""

from typing import ClassVar
from uuid import UUID

from ergon_core.core.runtime.events.base import InngestEventContract


class RunCancelledEvent(InngestEventContract):
    """Emitted to cancel all in-flight Inngest functions for a run."""

    name: ClassVar[str] = "run/cancelled"

    run_id: UUID


class RunCleanupEvent(InngestEventContract):
    """Emitted after workflow completion/failure to trigger sandbox cleanup."""

    name: ClassVar[str] = "run/cleanup"

    run_id: UUID
    status: str
    error_message: str | None = None
