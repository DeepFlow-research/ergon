"""Public benchmark-owned task type."""

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Generic, TypeVar, cast
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, model_serializer

from ergon_core.api._serialization import (
    TaskDefinitionJson,
    component_type_path,
    import_component,
    import_component_subclass,
)

if TYPE_CHECKING:
    from ergon_core.api.rubric.evaluator import Evaluator
    from ergon_core.api.sandbox.sandbox import Sandbox
    from ergon_core.api.worker.worker import Worker

logger = logging.getLogger(__name__)


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
    """Runtime task passed to Worker.execute().

    Per PR 2 of the v2 authoring API redesign, `task_id` lives as a
    `PrivateAttr` set by `Task.from_definition`. The `task_id` property
    raises if read before materialization — surfaces the bug at the
    boundary instead of producing a Task with an unset identity.

    Object-bound fields are the only public shape: every persisted task
    snapshot carries its worker, sandbox, and evaluators directly.
    """

    model_config = ConfigDict(frozen=False, arbitrary_types_allowed=True, extra="forbid")

    task_slug: str
    instance_key: str
    description: str
    parent_task_slug: str | None = None
    dependency_task_slugs: tuple[str, ...] = ()
    task_payload: PayloadT = Field(default_factory=EmptyTaskPayload)  # ty: ignore[invalid-assignment]

    worker: "Worker"
    sandbox: "Sandbox"
    evaluators: "tuple[Evaluator, ...]" = ()

    _task_id: UUID | None = PrivateAttr(default=None)

    @model_serializer(mode="wrap")
    def _serialize_with_type_discriminator(
        self,
        handler: Callable[..., dict[str, Any]],
    ) -> dict[str, Any]:
        """Inject ``_type`` discriminator so the snapshot can round-trip through
        ``Task.from_definition`` without losing which Task subclass was used.

        Pydantic's ``handler`` serializes ``worker``/``sandbox``/``evaluators``
        using the *declared* base-class schema (``Worker | None`` etc.), which
        drops subclass-specific fields (e.g. ``ReActWorker.toolkit``).  We
        re-serialize those three fields directly via the runtime objects'
        own ``model_dump`` so their full subclass schemas are used.
        """
        payload = handler(self)
        payload["_type"] = component_type_path(self)
        payload["worker"] = self.worker.model_dump(mode="json")
        payload["sandbox"] = self.sandbox.model_dump(mode="json")
        if self.evaluators:
            payload["evaluators"] = [ev.model_dump(mode="json") for ev in self.evaluators]
        return payload

    @property
    def task_id(self) -> UUID:
        if self._task_id is None:
            raise RuntimeError(
                f"Task {self.task_slug!r} has no task_id; it has not been materialized. "
                "Call Task.from_definition(...) or use the run-graph repository."
            )
        return self._task_id

    @classmethod
    async def from_definition(
        cls,
        task_json: TaskDefinitionJson,
        *,
        task_id: UUID,
        sandbox_id: str | None = None,
    ) -> "Task":
        """Reconstruct a Task from ``_type``-discriminated JSON and bind
        the per-run identity.

        ``sandbox_id`` semantics:

        - **Omit it** → config-only Task: ``task.sandbox`` is a frozen
          config object with ``_runtime = None``. Use on the orchestrator
          side (where the sandbox lifecycle is owned upstream) or in
          tests that don't need IO.
        - **Pass an existing sandbox_id** → live Task:
          ``task.sandbox._runtime`` is attached to the running external
          sandbox via ``Sandbox.from_definition(sandbox_json,
          sandbox_id=...)``. ``task.sandbox.run_command(...)`` works
          immediately.

        Object-bound Task snapshots carry nested ``worker``/``sandbox``/
        ``evaluators`` sub-objects, each with its own ``_type``. Each
        sub-object is re-inflated via its own ``from_definition``.
        """

        # Import the sub-component classes lazily to avoid cycles
        # (Worker / Sandbox / Evaluator all sit downstream of Task in
        # the api/ import graph).
        # reason: avoid circular import — Worker/Sandbox/Evaluator import Task.
        from ergon_core.api.rubric.evaluator import Evaluator

        # reason: avoid circular import — Worker/Sandbox/Evaluator import Task.
        from ergon_core.api.sandbox.sandbox import Sandbox

        # reason: avoid circular import — Worker/Sandbox/Evaluator import Task.
        from ergon_core.api.worker.worker import Worker

        task_type = task_json.get("_type")
        if not isinstance(task_type, str):
            raise ValueError(
                f"Task snapshot is missing the required `_type` discriminator "
                f"(got {type(task_type).__name__}). Every persisted task must "
                f"carry `_type` — produced by `model_serializer` on Task "
                f"subclasses."
            )

        import_component(task_type)
        TaskCls = import_component_subclass(task_type, Task, kind="Task")
        scalar_fields: dict[str, Any] = {
            k: v
            for k, v in task_json.items()
            if k not in {"_type", "worker", "sandbox", "evaluators"}
        }
        instance = cast("Task", TaskCls.model_construct(**scalar_fields))

        worker_json = task_json.get("worker")
        if not isinstance(worker_json, dict):
            raise ValueError(
                f"Task snapshot for {task_id} has no object-bound worker (_type={task_type!r})."
            )
        instance.worker = Worker.from_definition(worker_json)

        sandbox_json = task_json.get("sandbox")
        if not isinstance(sandbox_json, dict):
            raise ValueError(
                f"Task snapshot for {task_id} has no object-bound sandbox (_type={task_type!r})."
            )
        instance.sandbox = await Sandbox.from_definition(
            sandbox_json,
            sandbox_id=sandbox_id,
        )

        evaluators_json = task_json.get("evaluators")
        if isinstance(evaluators_json, list) and evaluators_json:
            inflated: list[Evaluator] = []
            for ev_json in evaluators_json:
                if not isinstance(ev_json, dict):
                    raise ValueError(
                        f"Evaluator snapshot in task {task_id} must be a "
                        f"dict, got {type(ev_json).__name__}."
                    )
                inflated.append(Evaluator.from_definition(ev_json))
            instance.evaluators = tuple(inflated)

        instance._task_id = task_id
        return instance
