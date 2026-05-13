# PR 5 — Object-Bound Public API And Definition Writer Bridge

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` or
> `superpowers:executing-plans` to implement this plan task-by-task.

**Goal:** Add the v2 public authoring objects while keeping old
`TaskSpec`/`WorkerSpec` benchmarks writable.

**Architecture:** Introduce `Sandbox`, object-bound `Task`, serializable
`Worker`, public `Experiment`, and a definition-writer bridge that accepts
both old and new benchmark output shapes.

**Tech Stack:** Pydantic v2, public API exports, definition writer tests.

---

## Files

**Create:**

```text
ergon_core/ergon_core/api/experiment.py
ergon_core/ergon_core/api/sandbox/__init__.py
ergon_core/ergon_core/api/sandbox/runtime.py
ergon_core/ergon_core/api/sandbox/sandbox.py
```

**Modify:**

```text
ergon_core/ergon_core/api/__init__.py
ergon_core/ergon_core/api/benchmark/task.py
ergon_core/ergon_core/api/benchmark/benchmark.py
ergon_core/ergon_core/api/worker/worker.py
ergon_core/ergon_core/api/criterion/criterion.py
ergon_core/ergon_core/api/rubric/rubric.py
ergon_core/ergon_core/api/rubric/evaluator.py
ergon_core/ergon_core/api/errors.py
ergon_core/ergon_core/core/application/experiments/definition_writer.py
ergon_core/ergon_core/core/domain/experiments/validation.py
ergon_core/tests/unit/api/
ergon_core/tests/unit/runtime/test_experiment_definition_service.py
```

## Current State

`Experiment` lives under `core.domain.experiments` and binds:

```python
workers: Mapping[str, WorkerSpec]
evaluators: Mapping[str, Evaluator]
assignments: Mapping[str, str | Sequence[str]]
```

`TaskSpec` carries evaluator binding keys but not concrete objects.

## Target State For This PR

New authoring code can write:

```python
Experiment(
    benchmark=BenchThatReturnsTasks(dataset_path="fixtures/minif2f.jsonl"),
    name="mini",
    description="MiniF2F smoke definition",
    metadata={"created_by": "test"},
)
```

and benchmark instances return:

```python
Task(
    task_slug="solve",
    instance_key="sample-1",
    description="Prove the theorem.",
    worker=ReActWorker(
        name="solver",
        model="openai:gpt-4o-mini",
        system_prompt="Write a Lean proof.",
        max_iterations=8,
    ),
    sandbox=LeanSandbox(lean_version="4.7.0"),
    evaluators=(Rubric(name="default", criteria=()),),
)
```

Old `TaskSpec` benchmarks still persist through a bridge.

## Task 1: Add Sandbox API

**Files:**

- Create: `ergon_core/ergon_core/api/sandbox/runtime.py`
- Create: `ergon_core/ergon_core/api/sandbox/sandbox.py`
- Create: `ergon_core/ergon_core/api/sandbox/__init__.py`
- Modify: `ergon_core/ergon_core/api/errors.py`

- [ ] **Step 0: Add `SandboxNotLiveError` to `api/errors.py`**

```python
class SandboxNotLiveError(RuntimeError):
    """Raised when a Sandbox method that requires a live runtime is
    called on a sandbox whose `_runtime` is None.

    This is *deliberately* loud rather than a silent no-op. The v1
    sandbox-lifecycle audit found that silent-skip semantics on
    detach/terminate masked double-release and release-before-acquire
    bugs. v2 surfaces these immediately at the call site.

    Cases that raise:
    - `Sandbox.terminate()` called before `provision()` succeeded.
    - `Sandbox.terminate()` called twice.
    - `Sandbox.detach()` called before `_bind_runtime()`.
    - `Sandbox.detach()` called twice.
    - `task.sandbox.run_command(...)` (or any IO) on a config-only sandbox.

    Lifecycle owners (worker_execute) and eval workers must track
    sandbox state explicitly; silently no-oping here only hides bugs.
    """
```

Export from `api/__init__.py` alongside `Sandbox`.

- [ ] **Step 1: Add protocol**

```python
from collections.abc import Sequence
from typing import Protocol


class SandboxRuntime(Protocol):
    sandbox_id: str

    async def run_command(self, cmd: str | Sequence[str], *, timeout: int | None = None): ...
    async def write_file(self, path: str, content: bytes) -> None: ...
    async def read_file(self, path: str) -> bytes: ...
    async def list_files(self, path: str) -> list[str]: ...
    async def close(self) -> None: ...
```

- [ ] **Step 2: Add base class**

```python
class Sandbox(BaseModel, ABC):
    model_config = {"frozen": False, "arbitrary_types_allowed": True}

    env: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: int | None = None
    requires_network: bool = False
    output_path: str = "/workspace/final_output/"
    _runtime: SandboxRuntime | None = PrivateAttr(default=None)

    @abstractmethod
    async def provision(self) -> None:
        """Provision a fresh external sandbox; attach _runtime to it."""

    @abstractmethod
    async def _bind_runtime(self, sandbox_id: str) -> None:
        """Re-attach _runtime to an EXISTING external sandbox by id.

        Called by Sandbox.from_definition when sandbox_id is passed.
        Authors implement this to connect to an already-running sandbox
        (e.g. e2b's AsyncSandbox.connect(sandbox_id)) rather than
        provision a new one.
        """

    @classmethod
    async def from_definition(
        cls,
        sandbox_json: TaskDefinitionJson,
        *,
        sandbox_id: str | None = None,
    ) -> "Sandbox":
        """Inflate a Sandbox from JSON, optionally attached live.

        - If sandbox_id is None, return a config-only sandbox
          (_runtime = None). Caller can later call provision() to make
          it live, or pass to authors who only need config (e.g. a
          static benchmark loader).
        - If sandbox_id is passed, attach to the running sandbox
          before returning. The returned instance is fully live;
          callers can immediately use run_command / write_file / etc.
        """

        sandbox_type = sandbox_json.get("_type")
        if not isinstance(sandbox_type, str):
            raise ValueError(
                f"Sandbox snapshot is missing the required `_type` "
                f"discriminator (got {type(sandbox_type).__name__}). Every "
                f"persisted sandbox must carry `_type`. Soft-defaulting "
                f"would silently produce the wrong Sandbox subclass."
            )
        SandboxCls = _import_component(sandbox_type)
        instance = cast("Sandbox", SandboxCls.model_validate(sandbox_json))
        if sandbox_id is not None:
            await instance._bind_runtime(sandbox_id)
        return instance

    async def terminate(self) -> None:
        """Terminate the EXTERNAL sandbox AND drop the local handle.

        Called only by the lifecycle owner (worker_execute). Eval
        workers must use detach() instead. Raises
        `SandboxNotLiveError` if called on a sandbox that has no live
        runtime — this catches double-terminate and "terminate before
        acquire" programming errors, which are exactly the lifecycle
        bugs the v1 audit found. The caller knows whether a sandbox
        is live; do not soft-fail on this.
        """
        if self._runtime is None:
            raise SandboxNotLiveError(
                f"{type(self).__name__}.terminate() called on a sandbox "
                f"with no live runtime. Likely double-terminate or "
                f"terminate-before-acquire — both are lifecycle bugs."
            )
        await self._runtime.close()
        object.__setattr__(self, "_runtime", None)

    async def detach(self) -> None:
        """Drop the local _runtime handle; DO NOT terminate the external sandbox.

        Called by eval workers in their finally block after
        criterion.evaluate(). The external sandbox keeps running so
        other eval invocations and worker_execute's final release can
        still access it. Raises `SandboxNotLiveError` if called on a
        sandbox that has no live runtime — eval workers always attach
        before they detach, so a detach without a runtime is a
        programming error worth surfacing.

        `SandboxRuntime.close_local` is part of the protocol after
        PR 5 — runtimes that don't implement it fail at protocol
        conformance, not silently here.
        """
        if self._runtime is None:
            raise SandboxNotLiveError(
                f"{type(self).__name__}.detach() called on a sandbox "
                f"with no live runtime. Eval workers must attach before "
                f"detaching — see Sandbox.from_definition(sandbox_id=...)."
            )
        await self._runtime.close_local()
        object.__setattr__(self, "_runtime", None)

    @property
    def is_live(self) -> bool:
        return self._runtime is not None

    def _require_runtime(self) -> SandboxRuntime:
        if self._runtime is None:
            raise SandboxNotLiveError(type(self).__name__)
        return self._runtime
```

The `_bind_runtime` / `detach` pair is the public surface a custom
`Sandbox` author has to think about. `from_definition` is framework
code that dispatches on the optional `sandbox_id`. The `SandboxRuntime`
protocol gets a `close_local()` method alongside `close()`:

```python
class SandboxRuntime(Protocol):
    sandbox_id: str

    async def run_command(self, cmd, *, timeout=None): ...
    async def write_file(self, path: str, content: bytes) -> None: ...
    async def read_file(self, path: str) -> bytes: ...
    async def list_files(self, path: str) -> list[str]: ...
    async def close(self) -> None: ...        # terminate external + close local
    async def close_local(self) -> None: ...  # close local only; leave external alive
```

For e2b-backed runtimes: `close()` calls `manager.terminate(...)` AND
the SDK's `sandbox.close()`. `close_local()` calls only the SDK's
`sandbox.close()` to drop the gRPC stream / TCP connection on this
process, leaving the cloud sandbox running for the next attach.

Add IO proxy methods on `Sandbox` so workers and criteria can call
`task.sandbox.write_file(...)` directly. Each method forwards to the
backing `SandboxRuntime` after checking `_require_runtime()`:

```python
    async def run_command(
        self,
        cmd: str | Sequence[str],
        *,
        timeout: int | None = None,
    ) -> CommandResult:
        runtime = self._require_runtime()
        effective_timeout = timeout if timeout is not None else self.timeout_seconds
        return await runtime.run_command(cmd, timeout=effective_timeout)

    async def write_file(self, path: str, content: bytes | str) -> None:
        runtime = self._require_runtime()
        payload = content.encode() if isinstance(content, str) else content
        await runtime.write_file(path, payload)

    async def read_file(self, path: str) -> bytes:
        runtime = self._require_runtime()
        return await runtime.read_file(path)

    async def list_files(self, path: str | None = None) -> list[str]:
        runtime = self._require_runtime()
        return await runtime.list_files(path or self.output_path)

    @property
    def sandbox_id(self) -> str:
        return self._require_runtime().sandbox_id
```

`CommandResult` is the existing DTO returned by
`SandboxRuntime.run_command`; export it from
`ergon_core.api.sandbox.runtime` alongside the protocol so test fixtures
in PR 12 can construct one directly. The `timeout_seconds` fallback is
load-bearing for the v1-audit regression where evaluators issued
sandbox commands with no timeout — see
[`08-decisions-log.md`](../08-decisions-log.md) "Sandbox IO methods on
base".

## Criterion / Evaluator signature note

Per [`01-api-surface.md` § Criterion class signature — locked](../01-api-surface.md),
PR 5 keeps the v1 `Criterion.evaluate(self, context: CriterionContext) -> CriterionOutcome`
signature unchanged. The earlier file-tree annotation suggesting
`evaluate(..., sandbox: Sandbox)` is superseded — the sandbox is
accessed via `context.task.sandbox` (live in the eval worker per Δ.5).

What PR 5 *does* change:

- `CriterionContext` loses its runtime proxy methods (`run_command`,
  `read_resource`, `write_file`, ...) — those now live on `Sandbox`.
- `CriterionContext._runtime` PrivateAttr is removed.
- `CriterionContext.sandbox_id` is removed — read via
  `context.task.sandbox.sandbox_id` if needed.
- `Criterion.from_definition(criterion_json: TaskDefinitionJson)`
  classmethod added (mirrors Task / Worker / Sandbox).
- `Rubric.evaluate(context)` aggregates per-criterion outcomes.

No criterion subclass in tree needs a method-signature rewrite —
only the criterion bodies that previously called
`context.run_command(...)` need to switch to
`context.task.sandbox.run_command(...)`. PR 6 (MiniF2F) is the first
real-world conversion; PR 10a/10b/10c carry the rest.

## Task 2: Add Object-Bound Task Fields

**Files:**

- Modify: `ergon_core/ergon_core/api/benchmark/task.py`

- [ ] **Step 1: Add fields to `Task`**

```python
worker: Worker | None = None
sandbox: Sandbox | None = None
evaluators: tuple[Evaluator, ...] = ()
```

They are nullable only in this PR so `TaskSpec` bridge snapshots can still
inflate. PR 11 makes worker and sandbox non-null.

- [ ] **Step 2: Update `Task.from_definition` to branch on snapshot shape and thread `sandbox_id`**

Replace the PR 2 body. `Task.from_definition` is async (already locked
in PR 2) and now awaits `Sandbox.from_definition(...)` so the optional
`sandbox_id` flows through.

```python
import logging

from ergon_core.api.criterion.criterion import Criterion
from ergon_core.api.rubric.evaluator import Evaluator
from ergon_core.api.rubric.rubric import Rubric
from ergon_core.api.sandbox.sandbox import Sandbox
from ergon_core.api.worker.worker import Worker


logger = logging.getLogger(__name__)


@classmethod
async def from_definition(
    cls,
    task_json: TaskDefinitionJson,
    *,
    task_id: UUID,
    sandbox_id: str | None = None,
) -> "Task":
    task_type = task_json.get("_type")
    if not isinstance(task_type, str):
        raise ValueError(
            f"Task snapshot is missing the required `_type` discriminator "
            f"(got {type(task_type).__name__}). Every persisted task must "
            f"carry `_type` — produced by `model_serializer` on Task "
            f"subclasses or by `_definition_task_snapshot` during the PR 1 "
            f"bridge."
        )
    TaskCls = _import_component(task_type)

    if TaskCls is TaskSpec or "_legacy" in task_json:
        # Bridge path: PR 1 wrote TaskSpec-shaped JSON for static nodes.
        # TaskSpec snapshots carry no object-bound sandbox, so sandbox_id
        # cannot be honored. Log a warning rather than silently ignoring,
        # because a non-None sandbox_id on the legacy branch is a strong
        # signal that a legacy snapshot reached an object-bound caller
        # (likely an unmigrated builtin) — exactly the kind of drift the
        # v1 audit was designed to surface.
        if sandbox_id is not None:
            logger.warning(
                "Task.from_definition: sandbox_id=%r passed for a "
                "TaskSpec/legacy snapshot (task_id=%s); cannot attach "
                "a live sandbox to a TaskSpec. Likely a legacy benchmark "
                "reached an object-bound code path — migrate the "
                "benchmark to return Task instances.",
                sandbox_id, task_id,
            )
        spec_json = {k: v for k, v in task_json.items() if k != "_legacy"}
        spec = TaskSpec.model_validate(spec_json)
        instance = Task(
            task_slug=spec.task_slug,
            instance_key=spec.instance_key,
            description=spec.description,
            parent_task_slug=spec.parent_task_slug,
            dependency_task_slugs=spec.dependency_task_slugs,
            evaluator_binding_keys=spec.evaluator_binding_keys,
            task_payload=spec.task_payload,
        )
    else:
        # Object-bound path: validate the Task subclass directly, then
        # re-inflate each nested component through its own discriminator.
        instance = cast("Task", TaskCls.model_validate(task_json))
        if isinstance(task_json.get("worker"), dict) and instance.worker is None:
            object.__setattr__(
                instance, "worker", Worker.from_definition(task_json["worker"])
            )
        if isinstance(task_json.get("sandbox"), dict) and instance.sandbox is None:
            object.__setattr__(
                instance,
                "sandbox",
                await Sandbox.from_definition(
                    task_json["sandbox"],
                    sandbox_id=sandbox_id,
                ),
            )
        elif instance.sandbox is not None and sandbox_id is not None:
            # Sandbox was already model_validate-ed but is config-only;
            # attach the runtime now.
            await instance.sandbox._bind_runtime(sandbox_id)
        elif instance.sandbox is None and sandbox_id is not None:
            # Caller wants a live sandbox but the snapshot carries no
            # Sandbox to attach to. Silent fall-through here would
            # produce a Task whose sandbox is None — every subsequent
            # `task.sandbox.run_command(...)` then explodes with a
            # confusing AttributeError far from the cause. Loud fail
            # here instead.
            raise ValueError(
                f"sandbox_id={sandbox_id!r} passed to Task.from_definition "
                f"but task snapshot has no sandbox to attach to "
                f"(task_id={task_id}, _type={task_type!r}). The eval-side "
                f"call site expects a live sandbox; the snapshot must "
                f"carry one."
            )
        evaluators_json = task_json.get("evaluators") or ()
        if evaluators_json and not instance.evaluators:
            inflated: list[Evaluator] = []
            for ev_json in evaluators_json:
                ev_type_raw = ev_json.get("_type")
                if not isinstance(ev_type_raw, str):
                    raise ValueError(
                        f"Evaluator snapshot in task {task_id} is missing "
                        f"the required `_type` discriminator "
                        f"(got {type(ev_type_raw).__name__})."
                    )
                ev_type = _import_component(ev_type_raw)
                if issubclass(ev_type, Rubric):
                    inflated.append(Rubric.model_validate(ev_json))
                elif issubclass(ev_type, Criterion):
                    inflated.append(Criterion.from_definition(ev_json))
                else:
                    inflated.append(ev_type.model_validate(ev_json))
            object.__setattr__(instance, "evaluators", tuple(inflated))

    object.__setattr__(instance, "_task_id", task_id)
    return instance
```

`Task.from_definition` is the only entry point that propagates
`sandbox_id`. Callers of `graph_repo.node(..., sandbox_id=...)` get a
live sandbox; callers who pass nothing get a config-only sandbox. The
bridge path is deleted in PR 11 along with `TaskSpec`.

## Task 2b: Convert Worker To Pydantic BaseModel

PR 6 expects `ReActWorker` to subclass a Pydantic `Worker`. Today `Worker` is
an `ABC` with a hand-rolled `__init__` (see
`ergon_core/ergon_core/api/worker/worker.py`). This step lands that conversion.

**Files:**

- Modify: `ergon_core/ergon_core/api/worker/worker.py`

- [ ] **Step 1: Replace the ABC base with a Pydantic ABC**

Replace the existing class body with:

```python
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator, Mapping
from importlib import import_module
from typing import Any, ClassVar, cast

from pydantic import BaseModel, ConfigDict, Field

from ergon_core.api.benchmark.task import Task
from ergon_core.api.errors import DependencyError
from ergon_core.api.worker.context import WorkerContext
from ergon_core.api.worker.results import WorkerOutput
from ergon_core.core.domain.generation.context_parts import ContextPartChunk
from ergon_core.core.infrastructure.dependencies import check_packages

WorkerStreamItem = ContextPartChunk | WorkerOutput


class Worker(BaseModel, ABC):
    """Base class for all workers. Pydantic-serializable."""

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=False)

    type_slug: ClassVar[str]
    required_packages: ClassVar[list[str]] = []
    install_hint: ClassVar[str] = ""

    # ClassVar declaring the Sandbox subclass a Worker requires. Default
    # is the base `Sandbox` (accepts any kind); concrete Worker
    # subclasses override to narrow (e.g. `LeanReActWorker.requires_sandbox
    # = LeanSandbox`). Validated at `Experiment` construction time;
    # see _validate_sandbox_compatibility in api/experiment.py.
    requires_sandbox: ClassVar[type["Sandbox"]] = Sandbox  # forward ref OK

    name: str
    model: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @abstractmethod
    async def execute(
        self,
        task: Task,
        *,
        context: WorkerContext,
    ) -> AsyncGenerator[WorkerStreamItem, None]:
        """Run the worker, yielding context chunks and a terminal WorkerOutput."""
        raise NotImplementedError

    @classmethod
    def from_definition(cls, worker_json: TaskDefinitionJson) -> "Worker":
        worker_type = worker_json.get("_type")
        if not isinstance(worker_type, str):
            raise ValueError(
                f"Worker snapshot is missing the required `_type` "
                f"discriminator (got {type(worker_type).__name__}). Every "
                f"persisted worker must carry `_type`."
            )
        WorkerCls = _import_component(worker_type)
        return cast("Worker", WorkerCls.model_validate(worker_json))

    def validate_runtime_deps(self) -> None:
        """Check that runtime dependencies are available."""
        errors = check_packages(
            self.required_packages,
            f"Worker '{self.type_slug}'",
        )
        if errors:
            parts = [*errors]
            if self.install_hint:
                parts.append(f"Install with: {self.install_hint}")
            raise DependencyError("\n".join(parts))
```

Notes:

- `Worker.validate(...)` is renamed to `validate_runtime_deps(...)` because
  Pydantic v2 reserves `validate` on `BaseModel`. Update the two known
  callers (`benchmark_loader.py`, `experiment.py`) in the same commit.
- `Worker.from_buffer` is intentionally **not** carried over; the textual
  ledger from PR 0 still names it, and PR 11 deletes the transitional ledger
  row. Any subclass that overrode it must move its state into
  `model_post_init` or an explicit factory classmethod (see CLAUDE.md
  "Do not use `model_post_init` to assemble core public API objects" — prefer
  the explicit factory).

- [ ] **Step 2: Add `_type` discriminator and import helper**

Add at the top of the module (sibling to `from_definition`):

```python
def _import_component(path: str) -> type[Any]:
    module_name, _, qualname = path.partition(":")
    if not module_name or not qualname:
        raise ValueError(f"Worker _type must be 'module:qualname', got {path!r}")
    obj: Any = import_module(module_name)
    for part in qualname.split("."):
        # typing: dynamic qualname walk — `part` is a user-controlled
        # discriminator path component, not a typed attribute name.
        obj = getattr(obj, part)
    if not isinstance(obj, type):
        raise TypeError(f"Worker _type {path!r} did not resolve to a class")
    return obj
```

Add a `_type` computed serialization field consistent with `Task`:

```python
@model_serializer(mode="wrap")
def _serialize(self, handler):
    payload = handler(self)
    payload["_type"] = f"{type(self).__module__}:{type(self).__qualname__}"
    return payload
```

- [ ] **Step 3: Subclass smoke test**

```python
def test_worker_baseclass_is_pydantic_and_serializes_type() -> None:
    class _Echo(Worker):
        type_slug = "echo"

        async def execute(self, task, *, context):  # noqa: ARG002
            yield WorkerOutput(final_text="ok")

    serialized = _Echo(name="e", model=None).model_dump()
    assert serialized["_type"].endswith(":_Echo")
    rebuilt = Worker.from_definition(serialized | {"_type": serialized["_type"]})
    assert rebuilt.name == "e"
```

Run:

```bash
uv run pytest ergon_core/tests/unit/api -k "worker_baseclass_is_pydantic" -q
```

## Task 3: Add Public Experiment

**Files:**

- Create: `ergon_core/ergon_core/api/experiment.py`
- Modify: `ergon_core/ergon_core/api/__init__.py`

- [ ] **Step 1: Add model**

```python
class Experiment(BaseModel):
    model_config = {"arbitrary_types_allowed": True}

    benchmark: Benchmark
    name: str | None = None
    description: str | None = None
    # First-class authoring-metadata fields. Anything the framework
    # reads (dashboard listing, audit, denormalized indexed columns)
    # lives here, not in `metadata`. `metadata` is for opaque
    # author-provided tags.
    created_by: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    _persisted: DefinitionHandle | None = PrivateAttr(default=None)

    @model_validator(mode="after")
    def _validate_sandbox_compatibility(self) -> "Experiment":
        for tasks in self.benchmark.build_instances().values():
            for task in tasks:
                if not isinstance(task, Task):
                    continue
                if task.worker is None or task.sandbox is None:
                    continue
                required = type(task.worker).requires_sandbox
                if not isinstance(task.sandbox, required):
                    raise SandboxKindMismatch(
                        task_id=task.task_id if task._task_id else uuid4(),
                        component=type(task.worker).__name__,
                        required=required,
                        actual=type(task.sandbox),
                    )
        return self
```

Use a generated UUID only for the error context during transition because
definition-time tasks do not yet have stable IDs in memory.

- [ ] **Step 2: Export it**

Add `Experiment`, `Sandbox`, and `SandboxRuntime` to
`ergon_core.api.__all__`.

## Task 4: Definition Writer Bridge

**Files:**

- Modify: `ergon_core/ergon_core/core/application/experiments/definition_writer.py`

- [ ] **Step 1: Add serializer**

```python
def _task_to_definition_json(task: Task | TaskSpec) -> dict:
    if isinstance(task, Task):
        return task.model_dump(mode="json")
    return {
        "_type": "ergon_core.api.benchmark.task:TaskSpec",
        **task.model_dump(mode="json"),
        "_legacy": True,
    }
```

- [ ] **Step 2: Write task JSON into definition rows**

In `definition_writer.py`, replace the existing task row construction
inside `persist_definition` (look for the loop that builds
`ExperimentDefinitionTask(...)`) with the snippet below. The new
`task_json` column lands here, not in PR 7 — PR 7 only adds metadata to
the parent `ExperimentDefinition` row:

```python
from ergon_core.core.persistence.definitions.models import (
    ExperimentDefinitionTask,
)


def _persist_task_rows(
    session: Session,
    *,
    definition_id: UUID,
    instance_id: UUID,
    instance_key: str,
    tasks: Sequence[Task | TaskSpec],
) -> None:
    for task in tasks:
        task_json = _task_to_definition_json(task)
        row = ExperimentDefinitionTask(
            definition_id=definition_id,
            instance_id=instance_id,
            instance_key=instance_key,
            task_slug=task.task_slug,
            description=task.description,
            task_payload_json=task_json.get("task_payload", {}),
            task_json=task_json,
        )
        session.add(row)
```

If `ExperimentDefinitionTask.task_json` does not exist yet, add it as part
of this PR with an additive Alembic migration (mirror the PR 1 migration
shape):

```python
def upgrade() -> None:
    op.add_column(
        "experiment_definition_tasks",
        sa.Column(
            "task_json",
            sa.JSON(),
            nullable=False,
            server_default="{}",
        ),
    )


def downgrade() -> None:
    op.drop_column("experiment_definition_tasks", "task_json")
```

The bridge serializer must be named `_task_to_definition_json` so PR 11
can grep-and-delete it as a single symbol when only `Task` remains.

## Task 4c: Lift `_DetachableSandboxBridge` Into `Sandbox.detach()`

PR 4 introduced `_DetachableSandboxBridge` as a stub so the reshaped
`evaluate_task_run` could compile before `Sandbox.detach()` existed.
Now that `Sandbox` is a real ABC, lift the bridge logic into the
base-class method (already defined in Task 1 Step 2 above) and delete
the bridge.

**Files:**

- Modify: `ergon_core/ergon_core/core/application/jobs/evaluate_task_run.py`
- Delete: `ergon_core/ergon_core/core/infrastructure/sandbox/runtime.py:_DetachableSandboxBridge`

- [ ] **Step 1: Replace bridge calls with the base method**

```python
# Before (PR 4):
await _DetachableSandboxBridge.detach(task.sandbox)

# After (PR 5):
await task.sandbox.detach()
```

- [ ] **Step 2: Delete the bridge class**

`git rm` the bridge or delete the symbol. Run:

```bash
rg "_DetachableSandboxBridge" ergon_core ergon_builtins
```

Expected: empty.

## Task 4b: Retire `_worker_from_payload_bridge` And Tighten Runtime Read Guard

PR 3 introduced `_worker_from_payload_bridge` in `worker_execute.py`. Now that
`Task` carries `worker` directly, the bridge must go and the architecture
guard must forbid `ComponentCatalogService` from creeping back into the
worker job body.

**Files:**

- Modify: `ergon_core/ergon_core/core/application/jobs/worker_execute.py`
- Modify: `ergon_core/tests/unit/architecture/test_runtime_read_boundaries.py`

- [ ] **Step 1: Replace bridge with `task.worker`**

In `worker_execute.py`, remove the bridge function and its import block:

```python
# Delete these:
from ergon_core.core.application.components.catalog import ComponentCatalogService

def _worker_from_payload_bridge(payload: WorkerExecuteJobRequest) -> Worker:
    ...
```

Replace the `worker = _worker_from_payload_bridge(payload)` call site with:

```python
worker = task.worker
if worker is None:
    raise ConfigurationError(
        f"Task {task.task_slug!r} has no bound worker; PR 5 requires "
        "object-bound workers on every Task snapshot.",
        run_id=payload.run_id,
        task_id=payload.task_id,
    )
worker.validate_runtime_deps()
```

The nullable `worker` field on `Task` is still permitted by the schema during
the transition (PR 11 makes it non-null); this runtime guard catches any
legacy snapshot that slipped through.

- [ ] **Step 2: Extend runtime read boundary guard**

Append to `test_runtime_read_boundaries.py`:

```python
def test_worker_execute_does_not_import_component_catalog() -> None:
    text = (
        ROOT
        / "ergon_core/ergon_core/core/application/jobs/worker_execute.py"
    ).read_text()
    assert "ComponentCatalogService" not in text, (
        "worker_execute must read worker from task.worker only — "
        "ComponentCatalogService imports recreate the registry-driven "
        "runtime that PR 5 removed."
    )
    assert "_worker_from_payload_bridge" not in text, (
        "PR 5 deletes the PR 3 worker payload bridge."
    )
```

- [ ] **Step 3: Run tests**

```bash
uv run pytest \
  ergon_core/tests/unit/architecture/test_runtime_read_boundaries.py \
  ergon_core/tests/unit/runtime/test_worker_execute_stream_contract.py -q
```

Expected: both pass; legacy bridge symbols absent.

## Task 5: Tests

**Files:**

- Modify: `ergon_core/tests/unit/api/test_public_api_imports.py`
- Modify: `ergon_core/tests/unit/runtime/test_experiment_definition_service.py`

- [ ] **Step 1: Add import test**

```python
def test_v2_public_api_exports_authoring_objects() -> None:
    from ergon_core.api import Experiment, Sandbox, Task, Worker

    assert Experiment is not None
    assert Sandbox is not None
    assert Task is not None
    assert Worker is not None
```

- [ ] **Step 2: Add definition-writer dual-shape test**

```python
import pytest
from sqlmodel import select

from ergon_core.api import Benchmark, Experiment, Task
from ergon_core.api.benchmark import BenchmarkRequirements, TaskSpec
from ergon_core.core.application.experiments.definition_writer import (
    persist_definition,
)
from ergon_core.core.persistence.definitions.models import (
    ExperimentDefinitionTask,
)
from tests.unit.runtime._test_workers import EchoWorker, EchoSandbox


class _LegacyBenchmark(Benchmark):
    benchmark_type = "test-legacy"
    requirements = BenchmarkRequirements()

    def build_instances(self):
        return {
            "default": (
                TaskSpec(
                    task_slug="legacy",
                    instance_key="sample-1",
                    description="legacy task",
                    evaluator_binding_keys=("default",),
                ),
            )
        }


class _ObjectBoundBenchmark(Benchmark):
    benchmark_type = "test-object-bound"
    requirements = BenchmarkRequirements()

    def build_instances(self):
        return {
            "default": (
                Task(
                    task_slug="object",
                    instance_key="sample-1",
                    description="object-bound task",
                    worker=EchoWorker(name="echo", model=None),
                    sandbox=EchoSandbox(),
                    evaluators=(),
                ),
            )
        }


@pytest.mark.asyncio
async def test_definition_writer_persists_both_legacy_and_object_bound(session):
    legacy_handle = persist_definition(
        Experiment(benchmark=_LegacyBenchmark(), name="legacy")
    )
    object_handle = persist_definition(
        Experiment(benchmark=_ObjectBoundBenchmark(), name="object-bound")
    )

    legacy_row = session.exec(
        select(ExperimentDefinitionTask).where(
            ExperimentDefinitionTask.definition_id == legacy_handle.definition_id
        )
    ).one()
    object_row = session.exec(
        select(ExperimentDefinitionTask).where(
            ExperimentDefinitionTask.definition_id == object_handle.definition_id
        )
    ).one()

    # Bridge path: TaskSpec snapshot is marked _legacy and carries
    # binding keys but no inline objects.
    assert legacy_row.task_json["_type"].endswith(":TaskSpec")
    assert legacy_row.task_json.get("_legacy") is True
    assert "worker" not in legacy_row.task_json
    assert legacy_row.task_json["evaluator_binding_keys"] == ["default"]

    # Object-bound path: full _type discriminators for every component.
    assert object_row.task_json["_type"].endswith(":Task")
    assert "_legacy" not in object_row.task_json
    assert object_row.task_json["worker"]["_type"].endswith(":EchoWorker")
    assert object_row.task_json["sandbox"]["_type"].endswith(":EchoSandbox")
    assert isinstance(object_row.task_json["evaluators"], list)
```

`EchoWorker` and `EchoSandbox` go in `tests/unit/runtime/_test_workers.py`
as minimal Pydantic implementations — keep them in the same module so other
PRs reuse them. If the helper module does not yet exist, create it in this
PR.

- [ ] **Step 3: Run focused tests**

```bash
uv run pytest ergon_core/tests/unit/api ergon_core/tests/unit/runtime/test_experiment_definition_service.py -q
```

## Task 6: Flip XFails Landed By This PR

**Files:**

- Modify: `ergon_core/tests/unit/architecture/test_v2_final_state_ledger.py`
- Modify: `ergon_core/tests/unit/architecture/test_dead_path_audit.py`

PR 5 introduces the object-bound public API and retires the two bridges
PR 3 / PR 4 introduced (`_worker_from_payload_bridge`,
`_DetachableSandboxBridge`).

- [ ] **Step 1: Remove `task_has_no_model_post_init` from `_XFAIL_BY_NAME`**

In `test_v2_final_state_ledger.py`, delete:

```python
"task_has_no_model_post_init": "PR 5 introduces object-bound Task",
```

- [ ] **Step 2: Remove the bridge entries from `_XFAIL_BY_SYMBOL`**

In `test_dead_path_audit.py`, delete:

```python
"_worker_from_payload_bridge": "PR 5: task.worker replaces the bridge",
"_DetachableSandboxBridge": "PR 5: lifted into Sandbox.detach()",
```

Both bridges are deleted by this PR's Task 4b and Task 4c.

- [ ] **Step 3: Run the ledgers**

```bash
uv run pytest \
  ergon_core/tests/unit/architecture/test_v2_final_state_ledger.py \
  ergon_core/tests/unit/architecture/test_dead_path_audit.py -q
```

Expected: three more cases PASS; remaining cases still XFAIL.

## PR Ledger

Invariant landed: object-bound authoring exists and persists beside old
TaskSpec authoring.

Bridge code introduced: nullable `Task.worker`/`Task.sandbox`,
`_task_to_definition_json`, legacy `TaskSpec` validation path.

Bridge code retired: `_worker_from_payload_bridge` (introduced by PR 3) is
deleted. The runtime-read guard now forbids `ComponentCatalogService` in
`worker_execute.py`.

Old path still intentionally alive: `TaskSpec`, `WorkerSpec`, assignments,
registry lookups.

Deletion gate: PR 10 migrates all builtins; PR 11 deletes adapters.

Tests added or updated: public API exports and dual-shape definition writer.

Modules owned by this PR: public API and definition writer.
