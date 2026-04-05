"""Inngest event schemas for infrastructure domain.

These are the contracts for infrastructure-related Inngest events.
"""

from typing import ClassVar, Literal
from uuid import UUID

from h_arcane.core._internal.events.base import InngestEventContract


class RunCleanupEvent(InngestEventContract):
    """Event emitted after execution completes (success or failure).

    Triggers: run_cleanup to terminate sandbox and verify status.
    """

    name: ClassVar[str] = "run/cleanup"

    run_id: UUID
    status: Literal["completed", "failed"]
    error_message: str | None = None
