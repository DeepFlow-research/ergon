"""Public benchmark-owned task type."""

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Generic, TypeVar, cast
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, model_serializer

# Framework-internal serialization helpers live in a sibling module so
# the `class Task` definition is the first thing readers of this file
# see, not 30 lines of discriminator-resolution machinery.
from ergon_core.api._serialization import TaskDefinitionJson, import_component

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


class TaskSpec(BaseModel, Generic[PayloadT]):
    """Definition-time task template produced by benchmark authoring code."""

    model_config = {"frozen": True}

    task_slug: str
    instance_key: str
    description: str
    parent_task_slug: str | None = None
    dependency_task_slugs: tuple[str, ...] = ()
    evaluator_binding_keys: tuple[str, ...] = ()
    task_payload: PayloadT = Field(default_factory=EmptyTaskPayload)  # ty: ignore[invalid-assignment]


class Task(BaseModel, Generic[PayloadT]):
    """Runtime task passed to Worker.execute().

    Per PR 2 of the v2 authoring API redesign, `task_id` lives as a
    `PrivateAttr` set by `Task.from_definition`. The `task_id` property
    raises if read before materialization — surfaces the bug at the
    boundary instead of producing a Task with an unset identity.

    PR 5 adds the object-bound authoring fields (`worker`, `sandbox`,
    `evaluators`). They are nullable in PR 5 only so legacy
    ``TaskSpec`` snapshots from PR 1's bridge still inflate; PR 11
    makes ``worker`` and ``sandbox`` non-null.
    """

    model_config = ConfigDict(frozen=False, arbitrary_types_allowed=True)

    task_slug: str
    instance_key: str
    description: str
    parent_task_slug: str | None = None
    dependency_task_slugs: tuple[str, ...] = ()
    evaluator_binding_keys: tuple[str, ...] = ()
    task_payload: PayloadT = Field(default_factory=EmptyTaskPayload)  # ty: ignore[invalid-assignment]

    # Object-bound authoring fields (PR 5). TODO(PR 11): drop nullability
    # on worker and sandbox; once every builtin returns Task instances
    # the legacy TaskSpec bridge in from_definition goes away.
    worker: "Worker | None" = None
    sandbox: "Sandbox | None" = None
    evaluators: "tuple[Evaluator, ...]" = ()

    _task_id: UUID | None = PrivateAttr(default=None)

    @model_serializer(mode="wrap")
    def _serialize_with_type_discriminator(
        self,
        handler: Callable[..., dict[str, Any]],  # slopcop: ignore[no-typing-any]
    ) -> dict[str, Any]:  # slopcop: ignore[no-typing-any]
        """Inject ``_type`` discriminator so the snapshot can round-trip through
        ``Task.from_definition`` without losing which Task subclass was used.

        Pydantic's ``handler`` serializes ``worker``/``sandbox``/``evaluators``
        using the *declared* base-class schema (``Worker | None`` etc.), which
        drops subclass-specific fields (e.g. ``ReActWorker.toolkit``).  We
        re-serialize those three fields directly via the runtime objects'
        own ``model_dump`` so their full subclass schemas are used.
        """
        payload = handler(self)
        payload["_type"] = f"{type(self).__module__}:{type(self).__qualname__}"
        # TODO(PR 11): once PR 11 makes `worker` and `sandbox` non-
        # nullable on the object-bound path, drop the `is not None`
        # guards (the legacy TaskSpec-bridge branch in `from_definition`
        # is what produces None values today; PR 11 deletes it).
        if self.worker is not None:
            payload["worker"] = self.worker.model_dump(mode="json")
        if self.sandbox is not None:
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

        Two snapshot shapes are accepted:

        1. **TaskSpec bridge** (PR 1 legacy): JSON with
           ``_type=...:TaskSpec`` or a ``_legacy`` marker. Reshaped to a
           base ``Task`` with empty ``worker``/``sandbox``/``evaluators``
           (the legacy path predates object-bound binding). PR 11 drops
           this branch entirely along with ``TaskSpec``.
        2. **Object-bound Task** (v2): JSON with a Task subclass
           ``_type`` plus nested ``worker``/``sandbox``/``evaluators``
           sub-objects, each carrying their own ``_type``. Each sub-
           object is re-inflated via its own ``from_definition``.
        """

        # Import the sub-component classes lazily to avoid cycles
        # (Worker / Sandbox / Evaluator all sit downstream of Task in
        # the api/ import graph).
        # reason: avoid circular import — Worker/Sandbox/Evaluator import Task.
        from ergon_core.api.rubric.evaluator import Evaluator
        from ergon_core.api.sandbox.sandbox import Sandbox
        from ergon_core.api.worker.worker import Worker

        task_type = task_json.get("_type")
        if not isinstance(task_type, str):
            raise ValueError(
                f"Task snapshot is missing the required `_type` discriminator "
                f"(got {type(task_type).__name__}). Every persisted task must "
                f"carry `_type` — produced by `model_serializer` on Task "
                f"subclasses or by `_definition_task_snapshot` during the PR 1 "
                f"bridge."
            )
        TaskCls = import_component(task_type)

        if TaskCls is TaskSpec or "_legacy" in task_json:
            # TODO(PR 11): drop this entire bridge branch along with TaskSpec.
            if sandbox_id is not None:
                # TaskSpec snapshots carry no object-bound sandbox; the
                # caller asked for a live attach but there's nothing to
                # attach to. Log loudly — this is the kind of drift the
                # v1 audit was designed to surface (an unmigrated
                # benchmark reaching an object-bound code path).
                logger.warning(
                    "Task.from_definition: sandbox_id=%r passed for a "
                    "TaskSpec/legacy snapshot (task_id=%s); cannot attach a "
                    "live sandbox to a TaskSpec. Migrate the benchmark to "
                    "return Task instances.",
                    sandbox_id,
                    task_id,
                )
            spec_fields = {
                k: v for k, v in task_json.items() if k not in {"_type", "_legacy", "task_payload"}
            }
            spec = TaskSpec.model_validate(spec_fields)
            instance: Task = Task(
                task_slug=spec.task_slug,
                instance_key=spec.instance_key,
                description=spec.description,
                parent_task_slug=spec.parent_task_slug,
                dependency_task_slugs=spec.dependency_task_slugs,
                evaluator_binding_keys=spec.evaluator_binding_keys,
            )
        else:
            # Object-bound path: model_validate would fail on the abstract
            # ``Worker``/``Sandbox``/``Evaluator`` field types (Pydantic
            # tries to construct the base class from the nested JSON
            # without doing the discriminator dispatch). Pull those keys
            # out, validate the Task scaffolding, then re-inflate each
            # nested component via its own ``from_definition``.
            scalar_fields = {
                k: v for k, v in task_json.items() if k not in {"worker", "sandbox", "evaluators"}
            }
            instance = cast("Task", TaskCls.model_validate(scalar_fields))

            worker_json = task_json.get("worker")
            if isinstance(worker_json, dict):
                instance.worker = Worker.from_definition(worker_json)

            sandbox_json = task_json.get("sandbox")
            if isinstance(sandbox_json, dict):
                instance.sandbox = await Sandbox.from_definition(
                    sandbox_json,
                    sandbox_id=sandbox_id,
                )
            elif sandbox_id is not None:
                # Caller wants a live sandbox but the snapshot carries
                # no Sandbox to attach to. Silent fall-through would
                # produce a Task whose sandbox is None — every
                # subsequent task.sandbox.run_command(...) then explodes
                # with a confusing AttributeError far from the cause.
                # Loud fail here instead.
                raise ValueError(
                    f"sandbox_id={sandbox_id!r} passed to Task.from_definition "
                    f"but task snapshot has no sandbox to attach to "
                    f"(task_id={task_id}, _type={task_type!r}). The eval-side "
                    f"call site expects a live sandbox; the snapshot must "
                    f"carry one."
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
