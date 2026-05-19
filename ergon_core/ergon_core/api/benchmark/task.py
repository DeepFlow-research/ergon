"""Public benchmark-owned task type."""

from typing import Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, Field, PrivateAttr

# Framework-internal serialization helpers live in a sibling module so
# the `class Task` definition is the first thing readers of this file
# see, not 30 lines of discriminator-resolution machinery.
from ergon_core.api._serialization import TaskDefinitionJson, import_component


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
    """

    model_config = {"frozen": False}

    task_slug: str
    instance_key: str
    description: str
    parent_task_slug: str | None = None
    dependency_task_slugs: tuple[str, ...] = ()
    evaluator_binding_keys: tuple[str, ...] = ()
    task_payload: PayloadT = Field(default_factory=EmptyTaskPayload)  # ty: ignore[invalid-assignment]

    _task_id: UUID | None = PrivateAttr(default=None)

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
        """Reconstruct a Task from `_type`-discriminated JSON and bind
        the per-run identity.

        ``sandbox_id`` semantics (locked in PR 2, fully wired by PR 5):

        - **Omit it** (default ``None``) and you get a *config-only*
          Task — the inflated ``task.sandbox`` is a frozen config
          object with ``_runtime = None``. Use this on the orchestrator
          side (where ``worker_execute`` provisions a fresh sandbox)
          or in tests that don't need IO.
        - **Pass an existing sandbox_id** and the eval-side caller
          gets a *live* Task — ``task.sandbox._runtime`` is attached
          to the running external sandbox by ``Sandbox.from_definition``.
          ``task.sandbox.run_command(...)`` works immediately.

        PR 2 honors the parameter shape but treats it as a no-op:
        TaskSpec bridge snapshots don't carry an object-bound sandbox,
        so there's nothing to attach. PR 5 wires the live attach via
        ``Sandbox.from_definition(json, sandbox_id=...)``.

        Raises `ValueError` if `_type` is missing or non-string —
        there is no soft-default to a base `Task`, because doing so
        would silently drop the authored worker/sandbox/evaluator
        bindings.

        `from_definition` is **async** even in PR 2 to lock in the
        signature PR 5 needs (the live-attach side awaits the e2b
        SDK). The body doesn't await anything yet, but the protocol
        contract is the v2 final shape.
        """

        # TODO(PR 5): forward `sandbox_id` to `Sandbox.from_definition`
        # so eval workers get a live sandbox attached to `task.sandbox`.
        _ = sandbox_id
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
        if TaskCls is TaskSpec:
            # TODO(PR 5): drop this entire `TaskSpec` branch once
            # object-bound Task JSON replaces TaskSpec snapshots from
            # the bridge writer in `_definition_task_snapshot`.
            #
            # Transitional bridge: PR 1 wrote TaskSpec-shaped JSON for
            # static nodes. Re-shape into a base `Task` with the
            # bridge's flat structural fields. The benchmark-specific
            # `task_payload` is preserved as-is in the run-tier row;
            # the bridge path loses parametrized type-validation
            # because PR 1's snapshot is generic, not parametrized.
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
            instance = TaskCls.model_validate(task_json)
        instance._task_id = task_id
        return instance
