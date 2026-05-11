"""Public benchmark-owned task type."""

from __future__ import annotations

from typing import Any
from typing import Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, Field, PrivateAttr, SerializeAsAny, field_validator

from ergon_core.api._definition import (
    from_definition_dict,
    import_component_string,
    is_definition,
    to_definition_dict,
)
from ergon_core.api.evaluator import Evaluator
from ergon_core.api.errors import TaskNotMaterializedError
from ergon_core.api.sandbox.sandbox import Sandbox
from ergon_core.api.worker.worker import Worker


class EmptyTaskPayload(BaseModel):
    """Default payload for benchmarks that do not need task-specific data."""

    model_config = {"extra": "forbid", "frozen": True}


PayloadT = TypeVar(
    "PayloadT",
    bound=BaseModel,
    default=EmptyTaskPayload,
    covariant=True,
)


class Task(BaseModel, Generic[PayloadT]):
    """Unified definition/runtime task type."""

    model_config = {"arbitrary_types_allowed": True, "extra": "ignore", "frozen": False}

    task_slug: str
    instance_key: str
    description: str
    worker: SerializeAsAny["Worker"]
    sandbox: SerializeAsAny["Sandbox"]
    evaluators: tuple[SerializeAsAny["Evaluator"], ...] = ()
    parent_task_slug: str | None = None
    dependency_task_slugs: tuple[str, ...] = ()
    task_payload: PayloadT = Field(default_factory=EmptyTaskPayload)  # ty: ignore[invalid-assignment]

    _task_id: UUID | None = PrivateAttr(default=None)

    @field_validator("worker", mode="before")
    @classmethod
    def _inflate_worker(cls, value: Any) -> Any:  # slopcop: ignore[no-typing-any]
        if is_definition(value):
            return from_definition_dict(value)
        return value

    @field_validator("sandbox", mode="before")
    @classmethod
    def _inflate_sandbox(cls, value: Any) -> Any:  # slopcop: ignore[no-typing-any]
        if is_definition(value):
            return from_definition_dict(value)
        return value

    @field_validator("evaluators", mode="before")
    @classmethod
    def _inflate_evaluators(cls, value: Any) -> Any:  # slopcop: ignore[no-typing-any]
        if isinstance(value, (list, tuple)):
            return tuple(
                from_definition_dict(item) if is_definition(item) else item for item in value
            )
        return value

    @property
    def task_id(self) -> UUID:
        if self._task_id is None:
            raise TaskNotMaterializedError(
                f"Task {self.task_slug!r} has no task_id; it has not been materialized "
                "into a run yet."
            )
        return self._task_id

    @classmethod
    def from_definition(
        cls,
        task_json: dict[str, Any],  # slopcop: ignore[no-typing-any]
        *,
        task_id: UUID,
    ) -> "Task":
        """Reconstruct a task and bind its runtime identity."""
        task_cls = import_component_string(task_json["_type"])
        data = dict(task_json)
        data.pop("_type", None)
        instance = task_cls.model_validate(data)
        object.__setattr__(instance, "_task_id", task_id)
        return instance

    def to_definition(self) -> dict[str, Any]:  # slopcop: ignore[no-typing-any]
        """Serialize this task for persisted experiment definitions."""
        return to_definition_dict(self)

