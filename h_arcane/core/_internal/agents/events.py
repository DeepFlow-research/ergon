"""Inngest event schemas for agents domain.

These are the contracts for agent-related Inngest events.
"""

from typing import ClassVar

from h_arcane.core._internal.events.base import InngestEventContract


class RunStartEvent(InngestEventContract):
    """Event to start a run execution (legacy single-task execution).

    Triggers: worker_execute Inngest function.
    """

    name: ClassVar[str] = "run/start"

    experiment_id: str
    worker_model: str = "gpt-4o"
    max_questions: int = 10


class ExecutionDoneEvent(InngestEventContract):
    """Event emitted by worker_execute after successful task execution.

    Triggers: run_evaluate to begin evaluation.
    """

    name: ClassVar[str] = "execution/done"

    run_id: str
