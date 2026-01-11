"""Inngest event schemas for agents domain.

These are the contracts for agent-related Inngest events.
"""

from pydantic import BaseModel


class ExecutionDoneEvent(BaseModel):
    """Event data for execution/done event.

    Emitted by worker_execute after successful task execution.
    Triggers run_evaluate to begin evaluation.
    """

    run_id: str
