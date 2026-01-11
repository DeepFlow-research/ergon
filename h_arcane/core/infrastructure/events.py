"""Inngest event schemas for infrastructure domain.

These are the contracts for infrastructure-related Inngest events.
"""

from pydantic import BaseModel
from typing import Literal


class RunCleanupEvent(BaseModel):
    """Event data for run/cleanup event.

    Emitted after execution completes (success or failure).
    Triggers run_cleanup to terminate sandbox and verify status.
    """

    run_id: str
    status: Literal["completed", "failed"]
    error_message: str | None = None
