# 01 — API surface

> The public types authors construct, the design principles that produced
> them, and what `ergon_builtins` looks like once the smells are removed.
> See [`02-persistence-layer.md`](02-persistence-layer.md)
> for how these objects are persisted and reconstructed,
> [`03-runtime.md`](03-runtime.md) for what happens when one runs,
> and [`04-walkthrough.md`](04-walkthrough.md) for an end-to-end trace.

> **On phase tags `[P1]–[P4]`.** Inline phase tags in this document
> reference the v1 phase plan and remain only as historical provenance
> markers. The v2 implementation order is **different and smaller** —
> see [`09-implementation-plan.md`](09-implementation-plan.md). Read the
> tags as "this concept landed in v1's Pn batch"; they have no v2 force.

## Two surfaces, one public package

`ergon_core.api` exposes the entire framework contract. It splits — by
*usage moment*, not by *abstraction tier* — into two surfaces:

| Surface | Used at | Owns | Who constructs / consumes |
|---|---|---|---|
| **Definition-time** | Pre-run, in the author's process | `Benchmark`, `Task`, `Sandbox`, `Worker`, `Criterion`, `Rubric`, `Evaluator`, `Experiment` | Author constructs them; framework persists them |
| **Runtime** | Inside `worker.execute()` (rollout container) | `WorkerContext` (curated single-target operations) | Framework hands `WorkerContext` to `execute()`; workers invoke it. Toolkits / CLI that need batch / predicate / materialisation ops import the internal services in `core.application.*` directly — see [`03-runtime.md`](03-runtime.md) "Where the implementation lives" for what to import. |

Definition-time owns *what an experiment is*; runtime owns *what a worker
can do while one runs*. The split exists because the invariants differ
(definition-time is single-writer + frozen-after-define; runtime is
concurrent + scoped to `(run_id, task_id)` with a stricter
constraint set), but the public surface is one — `ergon_core.api` is the
only import path authors and workers ever use.

```python
from ergon_core.api import (
    # Definition-time (the nouns):
    Benchmark, Task, Sandbox, Worker, Criterion, Rubric, Evaluator, Experiment,
    WeightedCriterion,
    # Runtime:
    WorkerContext, WorkerStreamItem, SpawnedTaskHandle,
    # Public exception types:
    TaskNotMaterializedError, SandboxNotLiveError, SandboxKindMismatch,
    ContainmentViolation,
)
```

Flat layout, no `runtime` / `services` / `advanced` submodule. An
earlier design promoted three additional public service classes
(`GraphMutator`, `GraphInspector`, `ResourceInspector`) into
`ergon_core.api` to expose batch / cross-scope / CLI-tier operations
through a layered API; that was rolled back as scope creep for v1 (see
[`08-decisions-log.md`](08-decisions-log.md) "Layered public runtime
API" under Alternatives considered, and
[`09-implementation-plan.md`](09-implementation-plan.md) "What's deferred"). For v1, the
"escape hatch" is direct import from `ergon_core.core.application.*` —
the same path `ergon_builtins.tools.*` and the workflow CLI use today.

The rest of this doc covers the **definition-time** surface — the seven
types authors construct. The runtime surface is documented end-to-end in
[`03-runtime.md`](03-runtime.md), with example consumers in
[`04-walkthrough.md`](04-walkthrough.md).

## What `ergon_core.api/` looks like on disk

The full public surface, file by file, with phase tags ([P1]–[P4])
matching [`09-implementation-plan.md`](09-implementation-plan.md). Everything authors,
workers, toolkits, criteria, and the workflow CLI ever import via the
public path lives under this tree. Toolkits / CLI that need ops not
covered by `WorkerContext` import directly from
`ergon_core.core.application.*` (no boundary enforcement in v1; see
[`09-implementation-plan.md`](09-implementation-plan.md) "What's deferred").

Legend: **`[P1]`–`[P4]`** = phase from [`09-implementation-plan.md`](09-implementation-plan.md);
**ADD / MODIFY / DELETE** = action vs. today's tree.

```
ergon_core/ergon_core/api/
│
├── __init__.py                      # MODIFY — re-exports the public surface as a flat namespace
│                                    #   (only one import path: `from ergon_core.api import ...`)
│                                    #   Drops: TaskSpec, ComponentRegistry [P1]
│                                    #   Adds:  Sandbox, SandboxRuntime [P2], WeightedCriterion [P4],
│                                    #          SpawnedTaskHandle [P3],
│                                    #          new exception types [P2/P3]
│
│   ── Definition-time: the nouns authors construct ──
│
├── benchmark/
│   ├── __init__.py                  # MODIFY — re-export new from_definition entry points
│   ├── benchmark.py                 # MODIFY — Benchmark(ABC) gains from_definition classmethod [P1]
│   ├── task.py                      # MODIFY — Task(BaseModel): worker: Worker, sandbox: Sandbox,
│   │                                #   evaluators: tuple[Evaluator, ...] direct object bindings [P1/P3];
│   │                                #   _task_id PrivateAttr + task_id property [P3];
│   │                                #   from_definition classmethod [P3]
│   └── requirements.py              # unchanged — Requirements stays as a definition-time helper
│
├── sandbox/                         # ADD — entirely new subpackage [P2]
│   ├── __init__.py                  # ADD — re-exports Sandbox, SandboxRuntime
│   ├── sandbox.py                   # ADD — class Sandbox(BaseModel, ABC); abstract provision()/terminate();
│   │                                #   IO proxy methods (run_command, read_file, write_file, list_files);
│   │                                #   _runtime PrivateAttr; from_definition classmethod
│   └── runtime.py                   # ADD — class SandboxRuntime(Protocol) — the live backing object's contract
│
├── worker/
│   ├── __init__.py                  # MODIFY — re-export new shapes (incl. SpawnedTaskHandle)
│   ├── worker.py                    # MODIFY — Worker(BaseModel, ABC): execute(task, *, context, sandbox) [P1];
│   │                                #   from_definition classmethod [P1]
│   ├── context.py                   # MODIFY — WorkerContext gains curated single-target methods [P3]:
│   │                                #     IDs:    run_id, task_id, execution_id, definition_id
│   │                                #     impls:  _task_mgmt, _task_inspect, _resource_repo (PrivateAttr,
│   │                                #             internal services injected at job start)
│   │                                #     methods: spawn_task, cancel_task, refine_task, restart_task,
│   │                                #              subtasks, descendants, get_task, resources
│   └── results.py                   # MODIFY — adds WorkerStreamItem (discriminated union); keeps WorkerOutput
│                                    #   class SpawnedTaskHandle — return of WorkerContext.spawn_task;
│                                    #     .task_id, .wait() (lives here rather than in a separate types.py
│                                    #     since it's worker-runtime-specific)
│
├── criterion/
│   ├── __init__.py                  # MODIFY — re-export new shapes
│   ├── criterion.py                 # MODIFY — Criterion(BaseModel, ABC): evaluate(..., sandbox: Sandbox) [P4];
│   │                                #   from_definition classmethod [P1]
│   ├── context.py                   # MODIFY — CriterionContext becomes a pure data carrier [P4: proxies dropped]
│   └── results.py                   # unchanged — CriterionOutcome / EvidenceMessage / etc.
│
├── rubric/
│   ├── __init__.py                  # MODIFY — re-export WeightedCriterion
│   ├── rubric.py                    # MODIFY — Rubric: list[WeightedCriterion]; aggregation knobs [P4]
│   │                                #   class WeightedCriterion(criterion=, weight=) [P4 — split out from Criterion.weight]
│   ├── evaluator.py                 # MODIFY — Evaluator(ABC): directly embedded on Task.evaluators;
│   │                                #   Rubric is one impl; future evaluator kinds plug in here
│   └── results.py                   # unchanged — RubricResult and friends
│
├── errors.py                        # MODIFY — already holds DependencyError, CriterionCheckError;
│                                    # adds the new exception types:
│                                    #   TaskNotMaterializedError — task.task_id accessed before materialization [P3]
│                                    #   SandboxNotLiveError      — IO method called before sandbox.provision() [P2]
│                                    #   SandboxKindMismatch      — toolkit/criterion requires_sandbox unsatisfied [P2]
│                                    #   ContainmentViolation     — WorkerContext mutation targeting non-descendant [P3]
│
├── experiment.py                    # ADD [P1] — canonical home of class Experiment.
│                                    # Lifted out of ergon_core.core.domain.experiments — the
│                                    # composition root is part of the authoring contract, not an
│                                    # internal type that happens to be exposed. core.domain owns the
│                                    # *services* that act on it (validation, definition writing,
│                                    # launch); core.domain.experiments.experiment.py is DELETED.
│                                    # Becomes a Pydantic BaseModel with a @model_validator(mode="after")
│                                    # that runs the requires_sandbox compatibility check (see
│                                    # "Foundational change C" below for the class sketch).
│                                    # Decision in 08-decisions-log.md (resolved — re-export pattern rolled back).
│
└── registry.py                      # DELETE [P1] — ComponentRegistry replaced by _type discriminator
```

**Not in this tree (deferred):** an earlier draft added `graph.py`,
`resources.py`, and `types.py` to host three new public service classes
(`GraphMutator`, `GraphInspector`, `ResourceInspector`) plus the
intermediate value-objects (`SubtaskSpec`, `MaterializeResult`,
`TaskTreeView`, `NextActionHint`, `ResourceRef`). All rolled back as
scope creep — see [`09-implementation-plan.md`](09-implementation-plan.md) "What's
deferred" and [`08-decisions-log.md`](08-decisions-log.md) "Layered
public runtime API" for the rationale.

Out of scope for the public surface (intentionally — only the rollout
container ever uses them, never author code or workers):

- `SandboxLifecycleHub` lives in
  `ergon_core/core/infrastructure/sandbox/lifecycle.py` (framework
  internals). It tracks live sandboxes process-wide for retry-reconnect
  / quota / shutdown — purely the rollout job's concern.
- `RunGraphNodeView` lives next to the graph repository in
  `ergon_core/core/application/...` (framework internals). It's the
  typed return shape of `graph_repo.node(...)`, and only
  `worker_execute.py` ever reads one.
- `TaskManagementService`, `TaskInspectionService`,
  `RunResourceRepository`, the Command DTOs (`AddSubtaskCommand`,
  etc.), `SubtaskInfo`, `RunResourceView` all stay in
  `ergon_core/core/application/*`. They are the **implementation
  backend** for `WorkerContext`'s curated methods, *and* the direct
  import target for any toolkit / CLI / future consumer that needs ops
  outside the curated surface. The boundary is porous (no enforcement
  test) — that's deliberate v1 simplification, see
  [`09-implementation-plan.md`](09-implementation-plan.md) "What's deferred".

Two architectural rules this layout encodes:

1. **One import root for the curated surface.** Anything a benchmark /
   worker / criterion author needs is in `ergon_core.api`. Toolkits and
   the workflow CLI may also import from `ergon_core.core.application.*`
   when they need ops not covered by `WorkerContext`; that import path
   is documented as the v1 escape hatch.
2. **Concrete benchmark types live in `ergon_builtins`, not `ergon_core.api`.**
   `LeanSandbox`, `PythonSandbox`, `MiniF2FToolkit`, etc. are
   *implementations* shipped with the framework but not part of its
   public contract — third parties can ship their own concrete
   `Sandbox` subclasses without touching `ergon_core` (see
   [`03-runtime.md#sandbox-provisioning`](03-runtime.md#sandbox-provisioning)).

## Public exceptions

The exception types added by this redesign all live in `errors.py`
alongside the existing `DependencyError` and `CriterionCheckError`.
Pinned constructor signatures so toolkit/test code that constructs
or catches them has one canonical shape:

```python
class TaskNotMaterializedError(RuntimeError):
    """Raised by Task.task_id when accessed before from_definition has run.
    Indicates author code held onto a definition-time Task; the framework
    path always inflates first."""
    def __init__(self, message: str) -> None:
        super().__init__(message)


class SandboxNotLiveError(RuntimeError):
    """Raised by Sandbox IO methods (run_command, read_file, ...) when
    called before provision() has attached _runtime. Author tests that
    forget to provision get this, not an AttributeError."""
    def __init__(self, sandbox_kind: str) -> None:
        super().__init__(
            f"{sandbox_kind} method called before provision(); "
            "no live runtime attached."
        )
        self.sandbox_kind = sandbox_kind


class SandboxKindMismatch(TypeError):
    """Raised by Experiment.@model_validator when a task's directly bound
    worker (or one of its evaluators/criteria) declares requires_sandbox = X
    and the task has a Y sandbox where Y is not a subclass of X.
    Construction-time error; misconfigured experiments never reach the
    database."""
    def __init__(
        self, *,
        task_id: UUID, component: str,
        required: type[Sandbox], actual: type[Sandbox],
    ) -> None:
        super().__init__(
            f"task {task_id} ({component}) requires "
            f"a {required.__name__}, got {actual.__name__}"
        )
        self.task_id = task_id
        self.component = component
        self.required = required
        self.actual = actual


class ContainmentViolation(RuntimeError):
    """Raised by WorkerContext mutation/inspection methods when the target
    task_id is not a descendant of the calling worker's task_id. Logic
    bug, not a recoverable runtime condition; workers should not catch."""
    def __init__(self, *, target: UUID, ancestor: UUID, run_id: UUID) -> None:
        super().__init__(
            f"task_id={target} is not a descendant of {ancestor} in run {run_id}"
        )
        self.target = target
        self.ancestor = ancestor
        self.run_id = run_id
```

Construction conventions:

- `*` after `self` for any constructor with more than one argument so
  callers always read keyword-by-keyword. Single-string ctors
  (`TaskNotMaterializedError`, `SandboxNotLiveError`) take their one
  argument positionally.
- Each exception keeps its semantic context as instance attributes
  (`exc.component`, `exc.task_id`, etc.) for test assertions and
  structured logging — not just baked into the message string.
- All inherit from a sensible stdlib base (`RuntimeError`, `TypeError`,
  etc.) rather than the bare `Exception` so generic `except RuntimeError:`
  blocks behave reasonably.

## The five types

Five user-facing types, no Spec siblings, no central registry:

| Type | Authored as | Holds (public fields) | Holds (private runtime) | Receives at runtime |
|---|---|---|---|---|
| `Benchmark` | subclass | task generator, payload type | — | (definition-time only) |
| `Task` | instance | slug, description, payload, **worker**, **sandbox**, **evaluators**, deps | `_task_id` (set by runtime, read via `task.task_id` property) | (it's the thing passed) |
| `Sandbox` | subclass + instance (`LeanSandbox(...)`, `PythonSandbox(...)`) | env, timeout, requires_network + subclass-specific config (e.g. `lean_version`) | `_runtime` (set after `provision()`; backs `run_command` / `read_file` / etc.) | (provisioned by framework, passed into `execute` / `evaluate`) |
| `Worker` | instance | name, model, strategy config (prompt, max_iter…) | — (pure config + behavior) | `task`, `context`, `sandbox` |
| `Criterion` | instance | slug, description | — (pure config + behavior) | `task`, `worker_output`, `context`, `sandbox` |
| `Rubric` | instance (or subclass) | criteria + weights + aggregation | — | `task`, criterion outcomes |

## The unifying pattern: one class per concept, runtime as `PrivateAttr`

The recurring "Spec / Live / Manager" tripling we have today
(`SandboxSpec` / `Sandbox` / `SandboxManager`, `TaskSpec` / `Task` / runtime
DTOs, `WorkerSpec` / `Worker` / `ComponentRegistry`) is not an essential
property of the domain — it's a workaround for the fact that pydantic models
can't carry runtime state without leaking it into their public schema.

**`CriterionContext` already solves this in-tree** and we generalize from it.
A `CriterionContext` is one class with two layers:

- **Public pydantic fields** — `task`, `worker_result`, `sandbox_id`, etc.
  Serializable, declarative, what an author looks at.
- **Private runtime backdoor** — `_runtime: CriterionRuntime | None` as a
  `PrivateAttr`, set via `with_runtime(...)` by the framework after
  construction. Public proxy methods (`run_command`, `read_resource`,
  `write_file`, …) dispatch to it.

```python
# Today, in ergon_core/api/criterion/context.py
class CriterionContext(BaseModel):
    task: Task
    worker_result: WorkerOutput
    ...
    _runtime: Annotated[CriterionRuntime | None, SkipValidation] = PrivateAttr(default=None)

    async def run_command(self, command: str, timeout: int = 30):
        return await self._require_runtime().run_command(command, timeout)
```

The pattern works. The author constructs a `CriterionContext` with public
fields; the runtime attaches `_runtime`; downstream consumers call
`context.run_command(...)` and don't care whether they're in a test that
faked the runtime or in a live container that wired the real one. **There is
no parallel `CriterionContextSpec` and no `CriterionContextManager`** — and
nobody misses them.

We apply the same shape to `Task` and `Sandbox` to collapse the duplicate
classes:

```python
class Task(BaseModel, Generic[PayloadT]):
    """Single Task type. ID is set by the runtime when materialized."""
    model_config = {"frozen": False}   # PrivateAttr requires non-frozen

    task_slug: str
    instance_key: str
    description: str
    worker: Worker                                           # NEW, direct object binding
    sandbox: Sandbox                                          # NEW, non-optional
    evaluators: tuple[Evaluator, ...] = ()                    # NEW, direct object binding
    parent_task_slug: str | None = None
    dependency_task_slugs: tuple[str, ...] = ()
    task_payload: PayloadT = Field(default_factory=EmptyTaskPayload)

    _task_id: UUID | None = PrivateAttr(default=None)

    @property
    def task_id(self) -> UUID:
        if self._task_id is None:
            raise TaskNotMaterializedError(
                f"Task {self.task_slug!r} has no task_id; it has not been "
                "materialized into a run yet. This is a framework error — "
                "worker code should never see a non-materialized Task."
            )
        return self._task_id

    # Note: there is no `_materialize` classmethod. The single
    # framework-only entry point is `from_definition` — defined in
    # 02-persistence-layer.md alongside the other class
    # `from_definition` conventions. It does construction + identity
    # binding in one call so the framework never holds a
    # half-materialized Task. Worker/evaluator objects are already part
    # of task_json and round-trip via their own `_type` discriminators.


class Sandbox(BaseModel, ABC):
    """Base for all sandbox kinds. Subclass to add a new kind of environment.
    Capabilities are live once `provision()` has been called and `_runtime`
    is attached."""
    model_config = {"frozen": False, "arbitrary_types_allowed": True}

    env: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: int | None = None
    requires_network: bool = False

    # `[v2: locked]` (Q28). The convention path under which workers and
    # criteria expect "task output" files to live. Each Sandbox subclass
    # picks its default; benchmarks that need a different path override
    # via the field. Replaces the v1 hardcoded `/workspace/final_output/`
    # in worker code AND in the resource publisher with one source of
    # truth on the sandbox itself.
    output_path: str = "/workspace/final_output/"

    _runtime: SandboxRuntime | None = PrivateAttr(default=None)

    # ── Subclass MUST implement ──
    @abstractmethod
    async def provision(self) -> None:
        """Spin up the underlying environment, install deps, attach
        ``self._runtime``. After this returns, ``self.is_live`` is True."""

    # ── Subclass MAY override (default = noop) ──
    async def terminate(self) -> None:
        """Tear down the underlying environment. Cheap sandboxes have nothing
        to clean up; expensive ones override."""
        pass

    # ── Inherited; subclasses get these for free via _runtime proxy ──
    @property
    def is_live(self) -> bool:
        return self._runtime is not None

    @property
    def sandbox_id(self) -> str:
        return self._require_runtime().sandbox_id

    async def run_command(
        self, cmd: str | Sequence[str], *,
        timeout: int | None = None,
    ) -> CommandResult:
        return await self._require_runtime().run_command(cmd, timeout=timeout)

    async def write_file(self, path: str, content: bytes | str) -> None:
        if isinstance(content, str):
            content = content.encode("utf-8")
        await self._require_runtime().write_file(path, content)

    async def read_file(self, path: str) -> bytes:
        return await self._require_runtime().read_file(path)

    async def list_files(self, path: str) -> list[str]:
        return await self._require_runtime().list_files(path)

    def _require_runtime(self) -> SandboxRuntime:
        if self._runtime is None:
            raise SandboxNotLiveError(
                f"{type(self).__name__} has no runtime attached; "
                "provision() has not been called yet. This is a framework "
                "error — worker code should never see a non-live Sandbox."
            )
        return self._runtime


# Concrete kind in ergon_builtins:
class LeanSandbox(Sandbox):
    lean_version: str = "4.7.0"
    e2b_template: str = "ergon-minif2f-v1"
    requires_network: bool = False

    async def provision(self) -> None:
        sb = await AsyncSandbox.create(template=self.e2b_template, envs=self.env)
        await sb.commands.run(f"elan default {self.lean_version}")
        object.__setattr__(self, "_runtime", _E2BSandboxRuntime(sb))

    async def terminate(self) -> None:
        if self._runtime is not None:
            await self._runtime.close()
```

**Author code constructs the typed subclass. Framework calls `provision()`
to attach the runtime. Worker/criterion code uses the inherited proxy
methods.** Same instance, two phases of life. No duplicate classes.

The "you constructed it wrong" failure mode is real but bounded — the only
two callsites that materialize a `Task` (one in `worker_execute.py`, one in
the dynamic-subtask path) and the only callsite that calls `provision()`
(the worker_execute job, just before invoking the worker) are framework
code. Author code never constructs these in their materialized form, so
the `_require_runtime()` errors only fire on framework bugs, which is
exactly when you want them.

For **Worker** and **Criterion**, no PrivateAttr is needed — they're pure
config + a single `execute`/`evaluate` method that takes everything runtime
through parameters. The pattern only applies where the type genuinely *has*
runtime capabilities (a sandbox to talk to, an ID minted by the framework).

## Subclass for *kind*, field for *config*

Adjacent rule that governs every other "should this be a subclass or a
field?" question this redesign raises:

- **Subclass when the *kind of thing* is genuinely different** — different
  shape, different operations, different lifecycle. The subclass is the
  identity; instances of it differ in config.
- **Field when the *configuration of a kind* varies** — same shape, same
  operations, just different data. No new subclass; just a different
  instance.

| Axis | Pattern | Examples |
|---|---|---|
| Worker strategies | subclass | `ReActWorker`, `TreeSearchWorker`, `SingleShotWorker` (each implements `execute()` differently) |
| Per-benchmark workers using ReAct | **field** (`toolkit`) | `ReActWorker(toolkit=MiniF2FToolkit(...))` — *not* `MiniF2FReactWorker(ReActWorker)` |
| Sandbox kinds | subclass | `LeanSandbox`, `PythonSandbox`, `LocalDockerSandbox`, `WasmSandbox` (each implements `provision()` differently) |
| Per-benchmark sandbox config | **field** (on the subclass) | `LeanSandbox(lean_version="4.7.0")`, `LeanSandbox(max_kill_time_seconds=600)` — *not* `MiniF2FLeanSandbox(LeanSandbox)` |
| Criteria | subclass | `LeanFileExists(Criterion)`, `WeightedSum(Criterion)` |
| Per-instance criterion config | **field** | `LeanFileExists(path="/workspace/proof.lean")` |

The smell with the original `MiniF2FReactWorker(ReActWorker)` was using
*subclassing* for what was actually *configuration* (same loop shape, just
different toolkit). The smell with the original
`Sandbox(template="lean", setup_payload={...})` was the opposite mistake —
using a stringly-typed *config* for what was actually a *kind* difference
(`provision()` for Lean+E2B is genuinely a different operation from
`provision()` for local-Docker-Python). Both fixes apply this same rule;
they just point in opposite directions because the original mistakes did.

The forcing question for any new "should this be a class or a field?"
decision: **does the subclass need its own behavior** (different
`execute`/`provision`/`evaluate` body), **or just different data**? If
behavior, subclass. If only data, field.

## What the framework sees (and what it doesn't)

Once we're using subclasses for kinds, the natural worry: if `LeanSandbox`
and `PythonSandbox` carry different config fields and possibly expose
different methods, how does the framework — which only knows the base
`Sandbox` — actually *invoke* anything that varies? The answer comes in
three parts, and the key principle is stronger than it usually gets stated.

**1. Subclass-specific config fields are invisible to the framework —
pydantic + the `_type` discriminator do all the work.**

`LeanSandbox(lean_version="4.7.0", e2b_template="ergon-minif2f-v1")` has
fields no other sandbox carries. The framework never reads them. At
construction time pydantic validates them against `LeanSandbox`'s schema,
not `Sandbox`'s. At persist time `model_dump()` includes
`_type: "ergon_builtins.sandboxes:LeanSandbox"` plus every subclass field.
At read time `Sandbox.from_definition(json)` does:

```python
SandboxCls = import_component_string(json["_type"])   # → LeanSandbox
return SandboxCls.model_validate(json)                # uses LeanSandbox schema
```

— pydantic uses the *subclass* schema for validation, so `lean_version`
parses correctly without any framework code mentioning it. The only place
that ever reads `self.lean_version` is `LeanSandbox.provision()`, which
gets dispatched polymorphically when the framework calls
`sandbox.provision()`.

The framework treats subclass config as opaque data. The "different
kwargs per subclass" problem disappears.

**2. Subclass-specific *methods* are invisible to the framework — only
consumers that import the subclass call them.**

> The base interface is the contract the *framework* needs from a Sandbox.
> Subclass-specific methods are the contract between a *consumer* (worker,
> criterion) and a particular sandbox kind. The framework never sees the
> second contract.

Concrete example: suppose `LeanSandbox` exposes
`compile_lean_file(path: str) -> CompileResult` that no other sandbox has.

| Caller | What it sees | Calls subclass methods? |
|---|---|---|
| `worker_execute` (framework job) | `Sandbox` (base) | No — only `provision()` / `terminate()` |
| `SandboxLifecycleHub` (framework) | `Sandbox` (base) | No — only `provision()` / `terminate()` |
| `MiniF2FToolkit.build_tools()` (worker-side) | imports `LeanSandbox` directly | Yes — calls `compile_lean_file` |
| `LeanProofValid.evaluate()` (criterion-side) | imports `LeanSandbox` directly | Yes — same |

`compile_lean_file` lives on `LeanSandbox`; the framework neither
references it nor needs to. The minif2f toolkit (which is already paired
with Lean by the experiment author) imports `LeanSandbox` and calls it
directly. Polymorphism handles the framework-facing interface
(`provision` / `terminate`); subclass-specific affordances bypass
polymorphism entirely.

The same applies to `Worker` (framework calls only `execute()`; everything
else is the subclass's private implementation) and `Criterion` (framework
calls only `evaluate()`).

**3. Workers that genuinely require a specific sandbox kind declare it —
once, at the binding.**

Most workers should be sandbox-agnostic and just use the base interface
(`sandbox.run_command(["lean", "--check", file])` works wherever Lean is
installed; the worker doesn't care which subclass is providing it). When
that's genuinely impossible — the worker needs typed access to subclass
methods or to the structured return shapes they give — the worker
declares its compatibility:

```python
class MiniF2FToolkit(_Toolkit):
    requires_sandbox: ClassVar[type[Sandbox]] = LeanSandbox

    def build_tools(self, sandbox: Sandbox, task: Task) -> list[AgentTool]:
        # Defensive isinstance — the Experiment validator (below) catches
        # mismatches at construction time, so this branch is dead code in
        # well-formed setups. Kept as a paranoia guard for hand-constructed
        # workers in tests; the live error is the SandboxKindMismatch the
        # validator raises before any rollout starts.
        assert isinstance(sandbox, self.requires_sandbox), (
            f"{type(sandbox).__name__} given to {type(self).__name__}"
        )
        # type-narrowed: sandbox is LeanSandbox here
        return [_compile_tool(sandbox.compile_lean_file), ...]
```

The framework checks `requires_sandbox` against `task.sandbox` in
`Experiment`'s `@model_validator(mode="after")` — i.e. at
`Experiment(...)` construction in the author's process, before
`persist_definition` runs. A misconfigured pairing raises
`SandboxKindMismatch` immediately and never reaches the database
or a rollout. The validator walks each task's directly bound
`task.worker` and `task.evaluators`; no experiment-level binding pool
or evaluator-key chase is involved. See
[`08-decisions-log.md`](08-decisions-log.md#alternatives-considered)
"Worker → Sandbox compatibility checking" for why the validator
lives on `Experiment` rather than per-`Task` or in the service
layer.

### The forcing test for what goes on the base

> A method belongs on the base interface **if and only if the framework
> code itself calls it.** Anything else lives on the subclass.

Apply that to the proposed `Sandbox` base:

| Method | Framework calls? | Verdict |
|---|---|---|
| `provision()` | Yes (`SandboxLifecycleHub.acquire`) | Base — framework contract |
| `terminate()` | Yes (`SandboxLifecycleHub.release`) | Base — framework contract |
| `run_command()`, `write_file()`, `read_file()`, `list_files()` | No — workers and criteria call these | **Convenience surface, not framework contract** |

This is a real wrinkle worth being honest about. The IO methods are
*useful* — every sandbox-backed worker wants them, and every E2B-backed
sandbox can implement them identically — but they're not part of the
framework contract; they're a shared convenience for sandbox-aware
consumers. Two ways to express that:

- **Default-implementations on the base** (current proposal): the base
  `Sandbox` declares these signatures; concrete kinds that *can* support
  them override; consumers get a uniform call site. The lie is small —
  every sandbox we'll ship in the foreseeable future implements them all,
  so no one trips on `NotImplementedError` in practice.
- **A `_RemoteIOSandbox` intermediate base** (`Sandbox` ← `_RemoteIOSandbox`
  ← `LeanSandbox`) that provides the IO methods. Any future sandbox kind
  that genuinely can't (e.g. a native-process `LocalSubprocessSandbox`)
  inherits straight from `Sandbox` and consumers fall back to
  `requires_sandbox = _RemoteIOSandbox`. Honest about the layering,
  slightly more boilerplate.

We pick the first for now — keep IO on the base for ergonomic uniformity,
document them as a "convenience surface" rather than a framework contract,
and revisit when a non-IO sandbox kind first appears (tracked in
[`08-decisions-log.md#open-questions`](08-decisions-log.md#open-questions)).
What we explicitly do **not** do under either scheme: add methods that
don't generalize (e.g. `compile_lean_file`) to the base. Those always
live on the subclass and are reached by consumers that import the
subclass directly.

The same shape governs `Worker` and `Criterion`. Framework-contract
method (`execute` / `evaluate`) on the base. Subclass-specific config in
typed pydantic fields. Subclass-specific methods invisible to the
framework, called only by consumers that imported the subclass.

## Foundational change A — Worker becomes serializable

Move `tools` out of `Worker.__init__`. Pass `sandbox` to `execute`.

```python
# Before
class MiniF2FReactWorker(ReActWorker):
    def __init__(self, *, name, model):
        super().__init__(name=name, model=model, tools=[], system_prompt=..., max_iterations=30)

    async def execute(self, task, *, context):
        sandbox = MiniF2FSandboxManager().get_sandbox(task.task_id)
        toolkit = MiniF2FToolkit(sandbox=sandbox, ...)
        self.tools = list(toolkit.get_tools())   # MUTATION — the smell
        async for item in super().execute(task, context=context):
            yield item

# After — framework interface only:
class Worker(BaseModel, ABC):
    """The entire framework-level worker interface.

    Knows about: task, context, sandbox.
    Knows nothing about: tools, toolkits, prompts, models, iterations,
    agents, LLMs, or any other per-strategy concept.
    """

    @abstractmethod
    async def execute(
        self, task: Task, *, context: WorkerContext, sandbox: Sandbox,
    ) -> AsyncGenerator[WorkerStreamItem, None]: ...
```

That's the whole framework contract. Everything else — including how
`ReActWorker` chooses to organize its config — is **implementation detail
of `ergon_builtins`, not part of the authoring API.**

**`sandbox` is non-optional.** The framework guarantees every worker
receives a live `Sandbox`. Every task picks a real, concrete template
(`"lean"`, `"swebench"`, `"research-e2b"`, `"python-3.13"`, …). The type
contract is uniform: `execute()` always gets a sandbox, no `None`-checks
anywhere in worker code.

**The discipline that matters:** the framework provides the **primitive**
(`sandbox: Sandbox`). The worker decides the **strategy** (ReAct? tree
search? single-shot? hand-coded? multi-agent?). The framework does not
mention tools, toolkits, prompts, models, agents, LLMs, or any other
shape that pre-supposes "agents look like X." Other worker strategies can
look completely unlike `ReActWorker` and be first-class — they implement
`execute(task, *, context, sandbox)` and that's it.

### How `ReActWorker` reorganizes (informative — not a framework concern)

This subsection describes how the existing `ReActWorker` in
`ergon_builtins` ends up shaped after the smell is removed. It is **not
a public-API contract** — `ergon_builtins` owns this and can change it.
Sketched here only because it determines what benchmark authors actually
type when they configure a ReAct-style worker.

The smell was that `ReActWorker` subclasses mutated `self.tools` inside
`execute()` because tools need a sandbox to construct. With `sandbox`
now passed to `execute()`, tool construction can move into the worker's
own internals. There are several reasonable shapes; the one we'd ship
collapses per-benchmark subclasses entirely:

```python
# In ergon_builtins.workers.baselines.react_worker — module-private:
class _Toolkit(BaseModel, ABC):
    """Internal to react_worker. Authors don't import the base directly;
    they import concrete toolkits like MiniF2FToolkit."""
    @abstractmethod
    def build_tools(self, sandbox: Sandbox, task: Task) -> list[AgentTool]: ...

class ReActWorker(Worker):
    name: str
    model: str | None
    system_prompt: str | None
    max_iterations: int
    _toolkit: _Toolkit              # _type-discriminated, JSON round-trips

    async def execute(self, task, *, context, sandbox):
        tools = self._toolkit.build_tools(sandbox, task)
        # ... pydantic-ai agent loop with `tools` ...

# In ergon_builtins.benchmarks.minif2f.toolkit — what already exists,
# made pydantic-serializable:
class MiniF2FToolkit(_Toolkit):
    lean_version: str = "4.7.0"
    ask_stakeholder: bool = False

    def build_tools(self, sandbox, task):
        # uses self.lean_version + sandbox to build pydantic_ai Tool list
        ...
```

Author code becomes one `ReActWorker` instance per role, no per-benchmark
worker subclasses anywhere:

```python
ReActWorker(name="prover-1", model="openai:gpt-4o", system_prompt="...",
             max_iterations=30,
             toolkit=MiniF2FToolkit(lean_version="4.7.0"))

ReActWorker(name="patcher", model="openai:gpt-4o", system_prompt="...",
             max_iterations=50,
             toolkit=SWEBenchToolkit(repo_url="...", timeout_s=600))
```

`MiniF2FReactWorker`, `SWEBenchReActWorker`, `GDPEvalReActWorker` all
**delete entirely** — they were "ReAct + tool list" combinations
masquerading as Worker subclasses. With `toolkit` as a field, the
combination is just an instance.

Other worker strategies in `ergon_builtins` (a hypothetical
`TreeSearchWorker`, `SingleShotWorker`, …) are free to ignore the
`_Toolkit` convention and shape their config however makes sense for
them. The framework neither sees nor cares.

## Foundational change B — Sandbox becomes a typed `Sandbox` subclass per kind

`Task.sandbox: Sandbox` is non-optional. The author picks the concrete
sandbox subclass that matches the task's environment kind:

```python
Task(sandbox=LeanSandbox(lean_version="4.7.0"))
Task(sandbox=PythonSandbox(pip_packages=("pandas", "requests")))
Task(sandbox=ResearchE2BSandbox())
Task(sandbox=LocalDockerSandbox(image="my-team/eval:latest"))
```

The base `Sandbox` class is `ABC` and not directly instantiable. Authors
must commit to a concrete kind — there's no `Sandbox(template="...")`
escape hatch. The class identity *is* the dispatch key; no parallel
template-string registry exists.

**No `"none"` / no-op sandbox.** A sandbox that satisfies the type
contract while no-op'ing `run_command` is a dangerous lie — it makes every
call site look uniform while making behavior surprising. The honest
options are:

- For tasks that genuinely use an environment, pick the real sandbox
  subclass that matches (`LeanSandbox`, `PythonSandbox`, etc.).
- For LLM-only or pure-orchestration tasks that we genuinely don't want
  to spin a container for: **out of scope for this redesign**. Land it
  later via a generic-Docker `DefaultPythonSandbox` (basic Python, no
  special setup) subclass — at least then `sandbox.run_command(...)`
  actually works rather than pretending to.

Until that generic subclass lands, every existing benchmark already has a
real sandbox it uses, so non-optional `Task.sandbox: Sandbox` is currently
satisfiable for the in-tree benchmarks without inventing the no-op.

Per-benchmark sandbox managers (`MiniF2FSandboxManager`,
`SWEBenchSandboxManager`, etc.) **delete entirely**. Each becomes a
`Sandbox` subclass that owns its own `provision()` / `terminate()` —
see [`03-runtime.md#sandbox-provisioning`](03-runtime.md#sandbox-provisioning)
for the full shape. Heterogeneous DAGs work natively because each Task
carries its own typed `Sandbox` subclass.

## Foundational change C — `Experiment` lifts into the public API

`Experiment` is the composition root authors construct around a benchmark
definition. The benchmark (via normal Python composition) produces Tasks
that already carry their workers, sandboxes, and evaluators. Today
`Experiment` lives in `ergon_core.core.domain.experiments` and is
imported into author code from there — a non-obvious path that pretends
the type is internal when in fact every benchmark constructor calls it
directly. This redesign **moves the class definition to
`ergon_core/api/experiment.py`** and deletes
`ergon_core/core/domain/experiments/experiment.py` — no re-export
indirection. The single import path is `from ergon_core.api import
Experiment`, in line with `Benchmark`, `Task`, `Worker`, `Sandbox`, etc.

What lives where after the lift:

| Concern | Lives in |
|---|---|
| `Experiment` class definition (the type itself) | `ergon_core/api/experiment.py` (this redesign) |
| `ExperimentValidationService` (cross-component rules engine) | `ergon_core/core/domain/experiments/validation.py` (unchanged location) — operates on the public `Experiment` instance |
| `DefinitionHandle` (return shape of `persist_definition`) | `ergon_core/core/domain/experiments/handles.py` (unchanged) — internal; held as `Experiment._persisted` PrivateAttr |
| `definition_writer.py`, `service.py`, `launch.py` | `ergon_core/core/application/experiments/` (unchanged) — import `Experiment` from `ergon_core.api` |

The class itself becomes a Pydantic `BaseModel` so it can host the
`requires_sandbox` `@model_validator(mode="after")` — see
[`08-decisions-log.md`](08-decisions-log.md) "Worker → Sandbox
compatibility checking" for why the validator lives here. The
runtime-only `_persisted` reference becomes a `PrivateAttr` (same
pattern as `Task._task_id`):

```python
# ergon_core/api/experiment.py
class Experiment(BaseModel):
    """Composition root for a benchmark definition. Tasks carry their
    worker/sandbox/evaluator objects directly; Experiment owns the
    benchmark as a whole plus run-level metadata."""
    model_config = {"frozen": False, "arbitrary_types_allowed": True}

    benchmark: Benchmark
    metadata:    Mapping[str, Any] = Field(default_factory=dict)

    _persisted: DefinitionHandle | None = PrivateAttr(default=None)

    @model_validator(mode="after")
    def _validate_sandbox_compatibility(self) -> "Experiment":
        """For each task, check `task.worker.requires_sandbox` and every
        directly bound evaluator/criterion's `requires_sandbox` against
        `task.sandbox`.
        Raises `SandboxKindMismatch` (canonical signature in
        "Public exceptions" above) at construction time, before
        `persist_definition` ever runs."""
        ...  # walk benchmark.tasks and inspect each task's direct objects
        return self
```

The `validate()` instance method that today wraps
`ExperimentValidationService` stays as-is — the cross-component rules
that aren't about `requires_sandbox` (task slugs unique, dependency slugs
resolve, etc.) keep living in the service layer and get called by
`definition_writer` before persisting. The pydantic
`@model_validator` only owns the type-driven sandbox check; everything
else stays in the explicit service so the rules are inspectable in one
place and don't run on every `Experiment(...)` construction in tests.

The old `Experiment.workers`, `Experiment.evaluators`, and
`Experiment.assignments` pools delete. The modularity they were trying
to provide moves into normal Python composition: benchmark factories can
accept different `Worker` / `Evaluator` objects and construct otherwise
identical `Task` graphs for cohort runs. The core model stays object-first
instead of exposing a mini dependency-injection container.

## Things that fall out for free

- **`TaskSpec` dies.** Single `Task` class with `_task_id` PrivateAttr (see above).
- **`SandboxSpec` and per-benchmark `*SandboxManager` classes die.** One
  abstract `Sandbox` base + one concrete subclass per environment kind
  (`LeanSandbox`, `PythonSandbox`, `LocalDockerSandbox`, …); each subclass
  owns its own `provision()` / `terminate()`. No allocator, no template
  registry, no string dispatch — `type(sandbox)` *is* the dispatch key.
- **`WorkerSpec` dies.** `Task.worker` carries a pre-constructed `Worker`
  instance, which is now a serializable pydantic model.
- **`ComponentRegistry`, `register_builtins`, `registry.publish`,
  `ComponentCatalogEntry` table, `ComponentCatalogService` all die.** The
  worker's class identity travels with each `Task.worker` as a `_type` discriminator
  in JSON: `{"_type": "ergon_builtins.workers...:ReActWorker", "name": ..., ...}`.
  The container does `import_component_string(json["_type"]).model_validate(json)`.
  Slugs survive only at the CLI surface as a static `BUILTIN_WORKERS = {slug:
  import_path}` dict in `ergon_builtins`.
- **Per-benchmark `MiniF2FReactWorker`/`GDPEvalReactWorker`/`SWEBenchReactWorker`
  delete entirely.** They were `ReActWorker` + a tool list pretending to
  be a class hierarchy. With `ReActWorker` taking `toolkit` as a field
  (see "How `ReActWorker` reorganizes" above), each benchmark just
  configures a `ReActWorker(toolkit=BenchmarkToolkit(...))` instance — no
  Worker subclass needed. The existing `MiniF2FToolkit`,
  `SWEBenchToolkit`, `GDPEvalToolkit` classes (already in tree) become
  pydantic-serializable and lose their `__init__(sandbox=...)` —
  `sandbox` moves to a `build_tools(sandbox, task)` method. The
  benchmark-specific environment bits (Lean install, repo clone) move
  out of the worker entirely and into the relevant `Sandbox` subclass's
  `provision()` (`LeanSandbox.provision()` does the Lean install,
  `SWEBenchSandbox.provision()` does the repo clone) — that's a sandbox
  concern, not a worker concern.
- **The whole `definition_task_id` / `node_id` / `task_id` confusion
  collapses to a single `task_id`** (see
  [`02-persistence-layer.md#identifier-model`](02-persistence-layer.md#identifier-model-two-tables-one-identity)).
  Born once at experiment-define (or spawn) time and carried unchanged
  through the pipeline. `WorkerContext` shrinks to the things that aren't
  on the task: `run_id`, `execution_id`, `definition_id`.
- **`CriterionContext` shrinks dramatically.** Its 12 proxy methods
  (`run_command`, `read_resource`, `write_file`, …) become "you have a
  `sandbox: Sandbox` and a `task: Task`, use them directly." The
  `_runtime` PrivateAttr that `CriterionContext` invented for its own use
  is exactly the pattern `Sandbox` now uses; the context shrinks to a
  pure data carrier.

## `TaskSpec` — resolved by the unified pattern

The earlier draft of this redesign left this as an open question with three
options. The unified `PrivateAttr`-for-runtime-state pattern subsumes it:
**there is one `Task`. Definition-time, `_task_id` is `None`; the public
`task_id` property raises if accessed. Materialization-time, the framework
sets `_task_id`; `task.task_id` returns the UUID.** No `TaskSpec` class, no
inheritance, no `task_id: UUID | None` propagation through downstream types.

The compile-time non-null guarantee from the previous "two-class" design
becomes a runtime invariant guarded by the property accessor. The narrowness
of the materialization callsite (one in `worker_execute.py`, one in the
dynamic-subtask path) makes this safe — author code can never reach a
materialized `Task` through a path that didn't go through the framework.

## Sandbox capability surface — locked `[v2: locked]` (Q24)

The exact methods the base `Sandbox` class exposes, locked at workshop.
Future PRs that want to add a method to the base must amend this section
first.

### Framework contract (must be implemented; framework calls these)

| Method | Signature | Notes |
|---|---|---|
| `provision` | `async def provision(self) -> None` | Abstract. Subclass spins up the underlying environment and attaches `self._runtime`. |
| `terminate` | `async def terminate(self) -> None` | Defaults to no-op. Override for environments that need teardown. |

That's the framework's actual contract — only these two are called by
`SandboxLifecycleHub`. Everything else on the base is a convenience for
worker / criterion authors.

### Convenience surface (every IO-backed sandbox implements these)

| Method | Signature | Purpose |
|---|---|---|
| `run_command` | `async def run_command(self, cmd: str \| Sequence[str], *, timeout: int \| None = None) -> CommandResult` | Run a shell command. Single-string is split per shell rules; `Sequence[str]` is exec-style. |
| `write_file` | `async def write_file(self, path: str, content: bytes \| str) -> None` | Write file at `path` inside the sandbox. `str` is UTF-8 encoded. |
| `read_file` | `async def read_file(self, path: str) -> bytes` | Read file from `path` inside the sandbox. |
| `list_files` | `async def list_files(self, path: str) -> list[str]` | Directory listing under `path`. Returns flat names, not absolute paths. |

These are documented as "convenience surface, not framework contract" —
the framework never calls them itself. They are inherited by every
sandbox subclass via the `_runtime` proxy. The day a sandbox kind that
genuinely cannot implement them appears (e.g. a hypothetical
`LocalSubprocessSandbox` with no remote IO), they get promoted onto a
`_RemoteIOSandbox` intermediate base; until then they live on the base
for ergonomic uniformity.

### Properties

| Property | Type | Purpose |
|---|---|---|
| `output_path` | `str` (field, defaults `"/workspace/final_output/"`) | Convention path for "task output" files. Overridable per subclass / instance. Replaces the v1 hardcoded path in worker code AND the resource publisher. |
| `is_live` | `bool` | True iff `provision()` has run and `_runtime` is attached. |
| `sandbox_id` | `str` (raises if not live) | Debug/tracing handle from the underlying runtime. |
| `env` | `dict[str, str]` (field) | Environment variables passed at provision time. Authors set; subclass `provision()` reads. |
| `timeout_seconds` | `int \| None` (field) | Default per-command timeout if not overridden by `run_command`'s `timeout=`. |
| `requires_network` | `bool` (field) | Authoring hint; subclass `provision()` decides whether to enable network. |

### Explicitly NOT on the base (kind-specific affordances)

The following are deliberately left for subclasses to add as needed:

- `compile_lean_file(path: str) -> CompileResult` — `LeanSandbox` only.
- `apply_patch(diff: str) -> PatchResult` — `SWEBenchSandbox` only.
- `execute_code(code: str, language: str) -> SandboxResult` — generic
  Python/REPL sandboxes only; in shell-based sandboxes use
  `run_command(["python", "-c", code])` directly.
- `read_resource(name: str) -> bytes` /
  `read_resource_by_id(id: UUID) -> bytes` — these are NOT on the
  sandbox; they live on `RunResourceRepository` (cross-cutting between
  sandbox and run state). Workers/criteria reach the resource repo via
  `WorkerContext.resources(...)` or by direct import. Sandbox is for
  per-sandbox filesystem; resource repo is for cross-task content
  storage. The two boundaries stay separate.
- `upload_files(files: list[dict]) -> None` — folded into the resource
  repo's materialise-into-sandbox helper. Not a sandbox method per se;
  it's a sandbox + resource-repo composition.

### Migration from v1's CriterionRuntime

v1's `CriterionRuntime` Protocol had `upload_files`, `execute_code`,
`cleanup`, `read_resource`, `read_resource_by_id` in addition to the
file/command methods. v2's split:

| v1 `CriterionRuntime` method | v2 home |
|---|---|
| `run_command` | `Sandbox.run_command` (base) |
| `write_file` | `Sandbox.write_file` (base) |
| `read_file` *(implicit)* | `Sandbox.read_file` (base) |
| `list_files` *(implicit)* | `Sandbox.list_files` (base) |
| `upload_files` | `RunResourceRepository.materialise_into(sandbox, ...)` (cross-cutting helper) |
| `execute_code` | subclass-specific (e.g. `PythonSandbox.execute_code`); not on base |
| `cleanup` | folded into `Sandbox.terminate` (rename) |
| `read_resource` | `RunResourceRepository.read_by_name` |
| `read_resource_by_id` | `RunResourceRepository.read_by_id` |

The split preserves "Sandbox = per-sandbox filesystem and process
runtime" as the base contract, with `RunResourceRepository` owning the
run-tier content store. Criteria that need both reach for both —
`Sandbox` via the `sandbox` parameter of `evaluate()`, repo via
`context.resources(...)` or direct import.

## Worker / Criterion non-pydantic runtime state — locked `[v2: locked]` (Q25)

`Worker` and `Criterion` are pydantic models. Their public fields are
serializable (round-trip through `_type` discriminator). But some
workers and criteria need *non-serializable* runtime state — HTTP
clients, model resolvers, in-memory caches.

The locked pattern for v2:

### Allowed

- **Construct fully at author init time.** Author writes
  `MyWorker(name="foo", model="gpt-4")`. All state needed by `execute()`
  either lives in public pydantic fields (config) or is built fresh
  inside `execute()` each call.
- **Classmethod factories.** `Worker.from_config(...)` / `Worker.from_env()`
  are fine — they're explicit constructors that produce a fully-wired
  instance. The factory does whatever expensive setup is needed (HTTP
  client warmup, credential lookup, …) before returning.
- **PrivateAttr set explicitly inside a classmethod / inside `execute`.**
  If a worker holds a non-serializable handle (e.g. a `ModelResolver`),
  the field is a `PrivateAttr` and the only way it gets populated is by
  an explicit assignment inside a factory or inside `execute()`.

### Disallowed

- **`model_post_init` for runtime state.** Pydantic's `model_post_init`
  runs implicitly after every construction (including
  `model_validate(...)` from JSON). Using it to lazy-init runtime
  resources means every JSON deserialization (e.g. cross-process
  reconstruction in `worker_execute`) tries to spin up an HTTP client
  before the runtime is ready. This is a class of v1 bug we're
  explicitly avoiding.
- **Lazy-init via `@property` that mutates state.** Same problem:
  hidden, time-varying behavior tied to method access rather than
  explicit lifecycle.

### Pattern in code

```python
class HttpClientWorker(Worker):
    """Worker that calls an external HTTP API."""
    name: str
    model: str
    api_base: str

    # NO model_post_init. NO @property that builds clients on first read.

    async def execute(self, task, *, context, sandbox):
        # Build the client fresh each execute() call. Cheap (httpx
        # client construction is microseconds); honest about lifecycle
        # (client lifetime == single execute() call); easy to test
        # (no global state).
        async with httpx.AsyncClient(base_url=self.api_base) as client:
            ...
```

```python
class CachedResolverWorker(Worker):
    """Worker that needs a long-lived model resolver."""
    name: str
    model: str

    _resolver: ModelResolver | None = PrivateAttr(default=None)

    @classmethod
    def from_config(cls, *, name: str, model: str) -> "CachedResolverWorker":
        """Explicit factory — populates _resolver at construction."""
        instance = cls(name=name, model=model)
        object.__setattr__(instance, "_resolver", ModelResolver(model))
        return instance

    async def execute(self, task, *, context, sandbox):
        if self._resolver is None:
            # Author called `CachedResolverWorker(...)` directly instead
            # of `from_config(...)`; that's an authoring error worth
            # surfacing. NOT silently building one here.
            raise RuntimeError(
                "CachedResolverWorker constructed without resolver; use "
                "CachedResolverWorker.from_config(...)"
            )
        ...
```

### Why this is locked

The "lazy-init via `model_post_init`" anti-pattern crashed v1 in
several places (sandbox creds resolved at construction time before env
was wired; HTTP clients built during Inngest event-handler boot before
the event loop was ready). v2 says: **state lifecycle is explicit, in
`__init__` or `from_config`, never `model_post_init`.** The cost is
slightly more boilerplate; the win is no more "why is this client
trying to connect on import?" debugging sessions.
