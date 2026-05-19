from typing import ClassVar, Literal
from uuid import UUID

from ergon_core.core.application.events.base import InngestEventContract


CancelCause = Literal[
    "manager_decision",
    "parent_terminal",
    "dep_invalidated",
    "downstream_invalidation",
    "run_cancelled",
]
PropagationCancelCause = Literal["parent_terminal", "dep_invalidated"]


class TaskCancelledEvent(InngestEventContract):
    name: ClassVar[str] = "task/cancelled"

    run_id: UUID
    definition_id: UUID
    task_id: UUID
    execution_id: UUID | None
    cause: CancelCause

    model_config = {"frozen": True, "extra": "allow"}
