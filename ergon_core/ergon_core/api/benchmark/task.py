"""Public benchmark-owned task type."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from typing import Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, Field, PrivateAttr, SerializeAsAny, field_validator

from ergon_core.api._definition import import_component_string, to_definition_dict
from ergon_core.api.errors import TaskNotMaterializedError

if TYPE_CHECKING:
    from ergon_core.api.rubric.evaluator import Evaluator
    from ergon_core.api.sandbox import Sandbox
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
        if cls._is_definition(value):
            from ergon_core.api.worker.worker import Worker

            return Worker.from_definition(value)
        return value

    @field_validator("sandbox", mode="before")
    @classmethod
    def _inflate_sandbox(cls, value: Any) -> Any:  # slopcop: ignore[no-typing-any]
        if cls._is_definition(value):
            from ergon_core.api.sandbox import Sandbox

            return Sandbox.from_definition(value)
        return value

    @field_validator("evaluators", mode="before")
    @classmethod
    def _inflate_evaluators(cls, value: Any) -> Any:  # slopcop: ignore[no-typing-any]
        if isinstance(value, (list, tuple)):
            from ergon_core.api.rubric.evaluator import Evaluator

            return tuple(
                Evaluator.from_definition(item) if cls._is_definition(item) else item
                for item in value
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

    @staticmethod
    def _is_definition(value: object) -> bool:
        return isinstance(value, dict) and "_type" in value


from ergon_core.api.sandbox import Sandbox  # noqa: E402
from ergon_core.api.worker.worker import Worker  # noqa: E402
from ergon_core.api.rubric.evaluator import Evaluator  # noqa: E402

Task.model_rebuild(
    _types_namespace={
        "Evaluator": Evaluator,
        "Sandbox": Sandbox,
        "Worker": Worker,
    }
)
