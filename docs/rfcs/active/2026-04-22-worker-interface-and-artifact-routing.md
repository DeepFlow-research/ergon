---
status: active
opened: 2026-04-22
author: deepflow-research
architecture_refs:
  - docs/architecture/01_public_api.md#core-abstractions
  - docs/architecture/06_builtins.md#core-abstractions
  - docs/architecture/cross_cutting/artifacts.md
supersedes: []
superseded_by: null
---

# RFC: Worker tool-interface cleanup + artifact→evaluator routing

## Problem

Three tangled problems have accumulated in PR #27 (`feature/real-llm-harness-infra`):

### 1. The `BenchmarkAdapter` ABC is the wrong abstraction

Commit `1ad4aac` (this branch) introduced a `BenchmarkAdapter(ABC)` at
`ergon_builtins/ergon_builtins/workers/baselines/adapters/base.py` with four
hooks — `build_tools`, `on_run_start`, `on_run_end`, `transform_output` — and
concrete `MiniF2FAdapter` / `SWEBenchAdapter` subclasses. The stated goal was
to remove per-benchmark `Worker` subclasses and make `ReActWorker` generic.

The hook surface is too wide:

- `on_run_start` and `build_tools` both let an adapter run setup code once
  per `execute()`. Which one "owns" sandbox creation / setup scripts? The
  SWE-Bench adapter puts the sandbox handle construction in `on_run_start`
  and the toolkit construction in `build_tools` — two hooks doing the same
  per-task prep because both are available.
- `transform_output` exists solely because the runtime drops
  `WorkerOutput.artifacts` on the durable path (see problem 2): adapters
  route artifacts back through `WorkerOutput.output` as a workaround. This
  is not a benchmark concern; it is a hole in the runtime's output
  serialization.
- `on_run_end` is a catch-all teardown hook. It is useful but is the third
  way to "run something per task" alongside `on_run_start` and `build_tools`.

For an LLM reading the ABC, four hooks read as "pick whichever one seems
right." The result is the exact duplication pattern in
`adapters/swebench.py` (`on_run_start` opens sandbox + runs setup scripts;
`build_tools` builds the toolkit; `on_run_end` captures patch;
`transform_output` routes it). Three of those four should not be
adapter concerns at all — they belong to the sandbox manager or the
criterion.

The worker's construction contract should be: **a list of tools and a
prompt**. Nothing more. Per-task setup belongs to the sandbox manager
(declarative, at sandbox boot). Artifact capture belongs to the criterion
(which already has the runtime surface it needs).

### 2. `WorkerOutput.artifacts` is dead on the durable path

Concrete drop point:
`ergon_core/core/runtime/inngest/worker_execute.py:144-147` —

```python
return WorkerExecuteResult(
    success=True,
    output_text=output.output,   # ← only .output survives
)
```

Everything in `output.artifacts` is discarded at this Inngest-step boundary.
Downstream:

- `ergon_core/core/runtime/inngest/execute_task.py:182` — passes only
  `output_text` to `finalize_success(FinalizeTaskExecutionCommand(...))`.
- `ergon_core/core/runtime/services/task_execution_service.py:270` — writes
  `output_text` into `RunTaskExecution.output_text`. **No `artifacts`
  column exists** on `RunTaskExecution`
  (`ergon_core/telemetry/models.py:96-151`).
- `ergon_core/core/runtime/inngest_executor.py:90-92` — artificially
  reconstructs `WorkerOutput(output=task_context.agent_reasoning,
  artifacts={})` for evaluator dispatch. `artifacts` is always `{}` by
  construction at that point.

### 3. `output_text` is a vague field name

`WorkerExecuteResult.output_text`, `FinalizeTaskExecutionCommand.output_text`,
and `RunTaskExecution.output_text` all carry the same thing: **the final
assistant-text message the agent emitted before the run terminated** —
the last `assistant_text` context event, verbatim. Not stdout, not a
summary, not a report.

"Output" is ambiguous in a codebase where "output" also refers to
sandbox command output (`CommandResult.stdout`), sandbox files under
`/workspace/final_output/`, and `WorkerOutput.output`. A reader can't
tell from the field name which thing it is.

So today the MiniF2F and SWE-Bench criteria read `worker.artifacts["proof"]`
/ `worker.artifacts["patch"]` — and the only reason those reads don't
return empty is that both adapters route the artifact into
`WorkerOutput.output` via `transform_output` as a workaround. The
`artifacts` dict on the return value is a red herring; the durable path
doesn't carry it.

The fix is not to add a `run_task_executions.artifacts_json` column. The
fix is to use the channels that already exist for file-shaped outputs:

- Workers write files into the sandbox under `/workspace/final_output/`.
- `SandboxResourcePublisher.sync()` auto-scans that directory before
  teardown and publishes every file as a content-addressed blob with a
  `run_resources` row.
- Criteria read what they need from the live sandbox
  (`CriterionRuntime.run_command`) or from the published blobs
  (`CriterionRuntime.read_resource` / `list_resources`), both of which
  already exist per RFC `2026-04-17-criterion-runtime-di-container.md`.

One helper is missing: a materializing "give me all files for this task"
convenience.

## Proposal

Four simultaneous cleanups, landed on PR #27.

### 1. Worker interface — tools + prompt, nothing else

Delete `ergon_builtins/workers/baselines/adapters/` entirely. `ReActWorker`
takes tools directly via a shared type alias:

```python
# ergon_core/ergon_core/api/types.py — NEW FILE
"""Shared type aliases for the public API surface."""

from typing import Any

type Tool = Any  # slopcop: ignore[no-typing-any]
"""Framework-agnostic tool carrier.

Intentionally unconstrained so workers can integrate with any agent
framework. ``ReActWorker`` passes these through to pydantic-ai's
``Agent(tools=...)``; nothing in our code enforces a structural protocol.
If we pin to pydantic-ai, tighten this.
"""
```

```python
# ergon_core/ergon_core/api/worker.py — base class tightens too
class Worker(ABC):
    def __init__(
        self,
        *,
        name: str,
        model: str | None,  # required, no default
        metadata: Mapping[str, Any] | None = None,
    ) -> None: ...
```

```python
# ergon_builtins/ergon_builtins/workers/baselines/react_worker.py
from ergon_core.api import Tool

class ReActWorker(Worker):
    def __init__(
        self,
        *,
        name: str,
        model: str | None,
        tools: list[Tool],
        system_prompt: str | None,
        max_iterations: int,
    ) -> None: ...
```

**All kwargs on both classes are required — no defaults.** Rationale:

- `model: str | None` — the union still carries meaning (`None` routes
  through the platform default resolver), but the `= None` default is
  dropped. Factories must declare the model they want, or explicitly
  pass `None` to opt into the resolver's fallback.
- `tools: list[Tool]` — no `| None` and no default. `None` and `[]`
  would be semantically identical, so the type loses the union; a
  tools-less ReAct loop is a degenerate shape and the caller should
  pass `[]` at the construction site so it's visible.
- `system_prompt: str | None` — `None` means "no instructions"
  (pydantic-ai receives `instructions=None`). The union stays; the
  default is dropped so the factory declares intent. Empty string is
  *not* a synonym for `None` — `""` would mean "instructions are
  literally the empty string," which is a legitimate (if weird)
  caller choice.
- `max_iterations: int` — no default. `10` was a silent guess carried
  over from the adapter migration; SWE-Bench wants ~50, MiniF2F is
  comfortable at ~10, future benchmarks will have their own budgets.
  Sharing a default means every new benchmark silently inherits `10`
  until a regression shows up. Force the factory to pick.

The base `Worker` class follows the same rule: `model` drops its
`= None` default. The anti-pattern ("nullable-with-default on worker
`__init__`") isn't about abstract vs. concrete — it's about hiding
sizing decisions, which applies everywhere in the class hierarchy.
Concrete `Worker` subclasses across the tree (`StubWorker`,
`SmokeTestWorker`, `ManagerResearcherWorker`, etc.) and their test
fixtures will all need to start passing `model=` explicitly. This is
the ripple cost we accept for a clean contract.

No `adapter` kwarg. No `on_run_start` / `on_run_end` / `transform_output`.
The worker's `execute()` just runs the ReAct loop over `self.tools` with
`self.system_prompt` for up to `self.max_iterations` nodes. It yields
`GenerationTurn`s. `get_output()` returns a `WorkerOutput` with the final
assistant text as `.output` and nothing in `.artifacts`.

Hoisting `Tool = Any` to `ergon_core.api.types` means call sites read as
"a list of tools" instead of "a list of anything" and the slopcop
`no-typing-any` ignore lives at exactly one definition site.

Per-benchmark registration becomes a factory closure that builds the
toolkit inline and passes the concrete tool list. Because all
`ReActWorker` kwargs are required, every sizing decision (model,
iteration budget, prompt) lives visibly in the factory.

The factory is invoked at `ergon_core/core/runtime/inngest/worker_execute.py:60`,
after the sandbox-setup step has run — so `task_id` and `sandbox_id`
are both in scope. The factory call signature grows those two kwargs
so benchmark factories can build toolkits bound to the live sandbox:

```python
# ergon_core/core/runtime/inngest/worker_execute.py — updated call
worker = worker_cls(
    name=payload.assigned_worker_slug,
    model=payload.model_target,
    task_id=payload.task_id,
    sandbox_id=payload.sandbox_id,
)
```

```python
# ergon_builtins/registry_core.py
def _swebench_react(
    *,
    name: str,
    model: str | None,
    task_id: UUID,
    sandbox_id: str,
) -> ReActWorker:
    sandbox = SWEBenchSandboxManager().get_sandbox(task_id)
    toolkit = SWEBenchToolkit(sandbox=sandbox, workdir="/workspace/repo")
    return ReActWorker(
        name=name,
        model=model,
        tools=list(toolkit.get_tools()),
        system_prompt=SWEBENCH_SYSTEM_PROMPT,
        max_iterations=50,
    )
```

Plain classes that don't need sandbox access (`StubWorker`,
`TrainingStubWorker`, etc.) are promoted to thin factory closures that
accept-and-ignore the extra kwargs, or the call site passes them
defensively — either shape is fine; plan writer decides.

**The bare `WORKERS["react-v1"] = ReActWorker` registry entry is
removed.** Under the new contract, `ReActWorker` can no longer be
instantiated with just `(name=, model=)` — there is no meaningful
registration for a "generic" ReAct worker because every real use
binds a concrete toolkit + prompt + iteration budget. Callers that
depended on the raw entry must migrate to a benchmark-specific
factory.

### 2. Setup scripts — move into `_install_dependencies`, fetch payload via queries

`BaseSandboxManager` already has a per-task hook that runs during
`create()`: the abstract `_install_dependencies(sandbox, task_id)`
method. Every benchmark manager already implements it (MiniF2F and
SWE-Bench as no-ops, GDPEval as pip install, ResearchRubrics as
workspace bootstrap). The reason SWE-Bench's hook is a no-op today is
that `task_id` alone is insufficient — the per-instance setup scripts
need `repo`, `base_commit`, `version`, `environment_setup_commit`, all
of which live in `ExperimentDefinitionTask.task_payload`.

**The data layer should expose that lookup, not the sandbox manager.**

Add one method to the existing `TaskExecutionsQueries` singleton at
`ergon_core/core/persistence/queries.py`:

```python
class TaskExecutionsQueries(BaseQueries[RunTaskExecution]):
    # ... existing methods unchanged ...

    def get_task_payload(self, task_execution_id: UUID) -> dict[str, Any] | None:
        """Return the immutable task_payload dict for a task execution.

        Joins ``run_task_executions`` → ``experiment_definition_tasks``.
        Returns ``None`` if the execution row doesn't exist or has no
        ``definition_task_id`` (run-scoped tasks that aren't tied to a
        definition).
        """
        with get_session() as session:
            stmt = (
                select(ExperimentDefinitionTask.task_payload)
                .join(
                    RunTaskExecution,
                    RunTaskExecution.definition_task_id == ExperimentDefinitionTask.id,
                )
                .where(RunTaskExecution.id == task_execution_id)
            )
            return session.exec(stmt).first()
```

`SWEBenchSandboxManager._install_dependencies` uses it:

```python
# ergon_builtins/benchmarks/swebench_verified/sandbox_manager.py

from ergon_core.core.persistence.queries import queries


class SWEBenchSandboxManager(BaseSandboxManager):
    async def _install_dependencies(
        self,
        sandbox: AsyncSandbox,
        task_id: UUID,
    ) -> None:
        payload = queries.task_executions.get_task_payload(task_id)
        if payload is None:
            raise SandboxSetupError(
                f"No task_payload for task_id={task_id}; "
                "prepare step must commit before sandbox-setup dispatches."
            )
        row = _payload_to_swebench_row(payload)
        harness = make_test_spec(row)
        for label, script in (
            ("setup_env", harness.setup_env_script),
            ("install_repo", harness.install_repo_script),
        ):
            r = await sandbox.commands.run(
                f"bash -c {shlex.quote(script)}",
                timeout=1800,
            )
            if r.exit_code != 0:
                raise SandboxSetupError(
                    f"swebench {label} failed: {(r.stdout or '')[-1000:]}"
                )
```

What this gets us:

- **`BaseSandboxManager.create()` signature unchanged.** No ripple on
  MiniF2F / GDPEval / ResearchRubrics.
- **DB access lives in the data layer** where it belongs — next to the
  sibling `get_by_task` / `get_latest_by_task` methods already on
  `TaskExecutionsQueries`.
- **Only benchmarks that need payload pay the DB round-trip.** MiniF2F's
  no-op hook stays a no-op.
- **No Inngest event-payload changes.** `SandboxSetupRequest` unchanged.

Once this lands, the workers and criteria can assume "sandbox exists ⇒
repo is cloned, deps are installed" for SWE-Bench. MiniF2F has no
equivalent per-task setup — the Lean container is ready at boot and its
`_install_dependencies` stays a no-op.

### 3. Artifact→evaluator routing — pull from sandbox or RunResources

Workers stop producing "artifacts" in the `WorkerOutput.artifacts` sense.
File-shaped outputs leave the worker one of two ways:

**A. Written to `/workspace/final_output/` in the sandbox.**
Already auto-published by `SandboxResourcePublisher.sync()` as blob-backed
`RunResource` rows before sandbox teardown.
Criterion reads via `context.runtime.read_resource(name)`.

**B. Left in the sandbox filesystem at a known path.**
Criterion runs commands directly via `context.runtime.run_command(...)` to
compute or extract what it needs.

Concrete application on this PR:

- **MiniF2F proof**: the `lean_write_file` tool writes to
  `/workspace/final_output/final_solution.lean` directly. Auto-published.
  Criterion does
  `proof = (await context.runtime.read_resource("final_solution.lean")).decode()`.

- **SWE-Bench patch**: the criterion computes the patch itself by running
  `cd /workspace/repo && git add -A && git diff HEAD` via
  `context.runtime.run_command(...)`. The patch never rides on
  `WorkerOutput`. The adapter's `_extract_patch` disappears.

#### New `CriterionRuntime` method: `get_all_files_for_task`

```python
# ergon_core/api/criterion_runtime.py — addition

async def get_all_files_for_task(self) -> dict[str, bytes]: ...
```

```python
# ergon_core/core/runtime/evaluation/criterion_runtime.py — addition

async def get_all_files_for_task(self) -> dict[str, bytes]:
    """Return {name: bytes} for every run_resource produced by this task.

    Scoped to the ``(run_id, task_execution_id)`` the runtime was
    constructed with. Not size-capped — callers that expect large
    resources should use ``list_resources()`` + ``read_resource()`` for
    selective reads instead.
    """
    with get_session() as session:
        stmt = (
            select(RunResource)
            .where(RunResource.run_id == self._run_id)
            .where(RunResource.task_execution_id == self._task_id)
            .order_by(RunResource.created_at.desc())  # type: ignore[arg-type]
        )
        rows = list(session.exec(stmt).all())

    # Keep the latest row per name; older revisions are skipped.
    seen: set[str] = set()
    out: dict[str, bytes] = {}
    for row in rows:
        if row.name in seen:
            continue
        seen.add(row.name)
        out[row.name] = Path(row.file_path).read_bytes()
    return out
```

Runtime is already task-scoped (the accepted RFC adds `task_id` to
`DefaultCriterionRuntime.__init__`); the helper takes no arguments —
passing a `task_id` in would invite criteria to read across tasks.

### 4. Rename `output_text` → `final_assistant_message`

Propagate the rename through the three layers that carry this value:

| Before | After | File |
|---|---|---|
| `WorkerExecuteResult.output_text` | `WorkerExecuteResult.final_assistant_message` | `ergon_core/core/runtime/services/inngest_function_results.py` |
| `FinalizeTaskExecutionCommand.output_text` | `FinalizeTaskExecutionCommand.final_assistant_message` | `ergon_core/core/runtime/services/task_execution_service.py` |
| `RunTaskExecution.output_text` (DB column) | `RunTaskExecution.final_assistant_message` (DB column) | `ergon_core/core/persistence/telemetry/models.py` + Alembic migration |

The name matches the `assistant_text` context event type that produces
this value — same vocabulary as the persistence layer. It also removes
the collision with `CommandResult.stdout` (which is also "output" in
casual English) and with files under `/workspace/final_output/`.

The DB column rename requires an Alembic revision (simple rename — no
data transform). Downstream readers in the dashboard API and the CLI
need updating in the same PR; grep pass will catch them.

#### `WorkerOutput.artifacts` — deprecated in place

The field stays on the model (it is on the public `Worker.execute()`
return contract and removing it would ripple into every Worker subclass
and test in the repo). It is marked deprecated with a docstring that says:

```python
class WorkerOutput(BaseModel):
    ...
    artifacts: dict[str, Any] = Field(  # noqa — deprecated
        default_factory=dict,
        description=(
            "DEPRECATED. This field is NOT carried across the durable "
            "worker→evaluator boundary (dropped at "
            "inngest/worker_execute.py). Do not use for files or data "
            "the criterion needs to read. Files → write to "
            "/workspace/final_output/ (auto-published as RunResources). "
            "Computed artifacts → have the criterion run commands in "
            "the sandbox via CriterionRuntime.run_command."
        ),
    )
```

Removal of the field is a follow-up once all built-in workers stop
writing to it.

## Invariants affected

### `docs/architecture/01_public_api.md#core-abstractions`

The `Worker` section should state clearly:

> The `Worker` base class and every concrete subclass declare their
> construction contract with **required keyword-only kwargs and no
> nullable-with-default fallbacks**. `Worker` takes `name: str`,
> `model: str | None` (required, no default); `ReActWorker` adds
> `tools: list[Tool]`, `system_prompt: str | None`, `max_iterations: int`
> — also required. A default value on worker `__init__` is an
> anti-pattern: it hides sizing decisions (iteration budget, model
> choice, system prompt) that should live visibly in the registry
> factory for each benchmark. Workers MUST NOT own per-task environment
> setup — setup belongs to the sandbox manager (see
> `BaseSandboxManager.create`). Workers MUST NOT return files or blobs
> through `WorkerOutput.artifacts` — the runtime serialization layer
> does not carry that field. Files → write to `/workspace/final_output/`.

### `docs/architecture/06_builtins.md`

Remove the "ReAct adapter composition" section added in commit
`a9819fe`. Replace with a "ReAct toolkit composition" section describing
the toolkit-as-list-of-tools pattern (no adapter ABC, no hooks).

Strengthen the anti-patterns list:

> - **Worker subclasses for per-benchmark glue.** Benchmark-specific
>   wiring is a factory-closure concern (registry), not a class hierarchy.
>   The worker `__init__` contract is `tools: list[Tool]` + prompt only.
> - **Per-task setup inside workers.** Setup scripts (clone, install deps,
>   environment bootstrap) belong to `BaseSandboxManager.create()` —
>   sandbox lifecycle, not worker lifecycle.
> - **Nullable-with-default kwargs on concrete Worker `__init__`.**
>   `tools: list[Tool] | None = None`, `max_iterations: int = 10`, etc.
>   hide sizing decisions in a shared default and mask per-benchmark
>   intent. Concrete workers declare their required construction
>   contract; factories pass every kwarg explicitly.

### `docs/architecture/cross_cutting/artifacts.md`

Add an "Invariants" item:

> - `WorkerOutput.artifacts` is a non-durable field. It is dropped at the
>   Inngest `worker_execute` step boundary and is not a channel to
>   criteria. File-shaped artifacts are published via
>   `SandboxResourcePublisher.sync()` from `/workspace/final_output/`;
>   criteria read them via `CriterionRuntime.read_resource(name)` or
>   `get_all_files_for_task()`. Computed artifacts (e.g. `git diff`) are
>   produced by the criterion itself via
>   `CriterionRuntime.run_command(...)`.

Also remove any "use `WorkerOutput.artifacts` for evaluator-visible data"
guidance if present.

### `docs/architecture/01_public_api.md#criterionruntime`

Add `get_all_files_for_task` to the method list. Update the surface-area
constraint note — the Protocol is now sandbox lifecycle (7) + resource
I/O (3 — adds `get_all_files_for_task`) + DB read (1) + event emission
(1) = 12 methods.

### `docs/architecture/04_sandbox_lifecycle.md` (per-task setup)

The invariant becomes:

> For benchmarks that require per-task environment setup (clone a
> specific commit, install version-pinned deps, apply a harness spec),
> that work runs inside `BaseSandboxManager._install_dependencies(
> sandbox, task_id)` — not inside the worker's `execute()`, not inside
> a separate `on_run_start` hook, and not inside the criterion. Managers
> that need per-task data (payload, instance-id metadata) read it from
> the data layer via `queries.task_executions.get_task_payload(task_id)`;
> `SandboxSetupRequest` carries only `task_id`, not the full payload.

### Naming invariant: `final_assistant_message`

The field that carries the agent's final assistant-text message is named
`final_assistant_message` end-to-end — from the Inngest
`WorkerExecuteResult` through `FinalizeTaskExecutionCommand` to the
`RunTaskExecution.final_assistant_message` column. Future work that
touches this field MUST NOT reintroduce `output_text` as a synonym, and
the rename MUST propagate into dashboard readers and any CLI surfaces in
the same PR that renames the column.

## Migration

All changes land in PR #27 (`feature/real-llm-harness-infra`). The PR
will not merge until this RFC is accepted.

### Files to delete

- `ergon_builtins/ergon_builtins/workers/baselines/adapters/__init__.py`
- `ergon_builtins/ergon_builtins/workers/baselines/adapters/base.py`
- `ergon_builtins/ergon_builtins/workers/baselines/adapters/minif2f.py`
- `ergon_builtins/ergon_builtins/workers/baselines/adapters/swebench.py`
- Any `tests/**/test_*adapter*.py` that target the deleted module.

### Files to add

| File | Purpose |
|---|---|
| `ergon_core/ergon_core/api/types.py` | New module holding the `Tool = Any` alias (and any future public type aliases). Re-exported from `ergon_core.api.__init__`. |

### Files to modify

| File | Change |
|---|---|
| `ergon_core/ergon_core/api/worker.py` | Drop `model: str \| None = None` default on the base `Worker.__init__`. `model` becomes required (union stays). |
| `ergon_builtins/workers/baselines/react_worker.py` | Remove `adapter` kwarg and the three hook call sites in `execute()`/`get_output()`. Tighten construction contract: `tools: list[Tool]`, `system_prompt: str \| None`, `max_iterations: int`, `model: str \| None` — all **required, no defaults**. Drop the internal `tools or []` / `max_iterations = max_iterations or 10` fallback branches. |
| `ergon_builtins/registry_core.py` | `_minif2f_react` / `_swebench_react` factories build toolkits inline and pass concrete `tools=` into `ReActWorker`. System prompts and `max_iterations` move here as plain constants. Factory call signature grows `task_id: UUID` and `sandbox_id: str` kwargs. **Remove** bare `"react-v1": ReActWorker` entry from `WORKERS`. Non-benchmark workers (`StubWorker`, `TrainingStubWorker`, `SmokeTestWorker`, `ManagerResearcherWorker`, etc.) either accept-and-ignore the new kwargs or get thin factory closures. |
| `ergon_core/core/runtime/inngest/worker_execute.py` | `worker_cls(...)` call at line ~60 passes `task_id=payload.task_id` and `sandbox_id=payload.sandbox_id` in addition to `name` / `model`. |
| `ergon_builtins/workers/baselines/stub_worker.py`, `training_stub_worker.py`, `smoke_test_worker.py`, `manager_researcher_worker.py`, `research_rubrics/stub_worker.py`, `stubs/canonical_smoke_worker.py` | Callers stop relying on `model` default. Either add explicit `model=` kwargs at construction sites, or tighten these subclasses to also require `model`. Plan writer picks the strategy. |
| Test fixtures that construct `Worker` subclasses without `model=` | Pass `model=None` (or a concrete value) explicitly. Grep for `StubWorker(name=`, `SmokeTestWorker(name=`, etc. Ripple is mechanical. |
| `ergon_core/core/persistence/queries.py` | Add `TaskExecutionsQueries.get_task_payload(task_execution_id)` — one new method, joins `run_task_executions → experiment_definition_tasks`, returns the payload dict. |
| `ergon_builtins/benchmarks/swebench_verified/sandbox_manager.py` | `_install_dependencies` stops being a no-op: reads `task_payload` via `queries.task_executions.get_task_payload`, builds the harness spec, runs `setup_env_script` + `install_repo_script`. |
| `ergon_builtins/benchmarks/swebench_verified/criterion.py` | `evaluate()` runs `git add -A && git diff HEAD` via `context.runtime.run_command` to get the patch. No read of `worker.artifacts["patch"]`. |
| `ergon_builtins/benchmarks/minif2f/criterion.py` (if it currently reads `worker.artifacts`) | Read proof via `context.runtime.read_resource("final_solution.lean")`. |
| `ergon_builtins/benchmarks/minif2f/toolkit.py` | `lean_write_file` writes to `/workspace/final_output/` so the publisher auto-captures it. |
| `ergon_core/api/results.py` | Docstring on `WorkerOutput.artifacts` marks it deprecated with explanation. |
| `ergon_core/api/criterion_runtime.py` | Add `get_all_files_for_task` to Protocol. |
| `ergon_core/core/runtime/evaluation/criterion_runtime.py` | Implement `get_all_files_for_task` on `DefaultCriterionRuntime`. |
| `ergon_core/core/runtime/services/inngest_function_results.py` | Rename `WorkerExecuteResult.output_text` → `final_assistant_message`. |
| `ergon_core/core/runtime/services/task_execution_service.py` | Rename `FinalizeTaskExecutionCommand.output_text` → `final_assistant_message`. Update write site. |
| `ergon_core/core/persistence/telemetry/models.py` | Rename `RunTaskExecution.output_text` column → `final_assistant_message`. |
| `ergon_core/alembic/versions/<new>.py` | Simple column rename; no data transform. |
| Dashboard API + CLI readers of `output_text` | Grep and rename. |
| `docs/architecture/01_public_api.md` | Update Worker contract + CriterionRuntime surface; document `Tool` alias. |
| `docs/architecture/06_builtins.md` | Replace adapter section with toolkit section; add anti-patterns entries. |
| `docs/architecture/cross_cutting/artifacts.md` | Add non-durability invariant for `WorkerOutput.artifacts`. |

### Tests to add / rewrite

- `tests/unit/test_react_worker.py` — construct `ReActWorker(tools=[…])`
  with fake tools; assert it runs loop and yields turns. No adapter
  fixtures.
- `tests/unit/test_swebench_sandbox_manager.py` — assert `create()` runs
  setup scripts, raises on non-zero exit.
- `tests/unit/test_swebench_criterion.py` — supply a mock
  `CriterionRuntime.run_command` that returns a canned `git diff HEAD`
  output; assert the criterion grades it correctly without touching
  `worker.artifacts`.
- `tests/unit/test_criterion_runtime_get_all_files.py` — unit test the
  new helper: task-scoped filter, dedup by name keeping newest, returns
  materialized bytes.
- Delete any existing `test_*adapter*` tests.

### Data migrations

None. No DB schema changes. `RunResource` already has the
`task_execution_id` column used by `get_all_files_for_task`.

## Alternatives considered

- **Add a `run_task_executions.artifacts_json` column and serialize
  `WorkerOutput.artifacts` there.** Rejected. This would preserve a field
  that is the wrong shape for the thing it tries to do: durable artifacts
  are files (potentially large, content-addressed, dedup-friendly) and
  we already have a table (`run_resources`) + a publisher
  (`SandboxResourcePublisher.sync()`) tuned for exactly that. Adding an
  `artifacts_json` column would duplicate half of `run_resources`
  inline on the task-execution row, with no size limit, no dedup, no
  blob storage.

- **Keep the adapter ABC but trim it to `build_tools` only.** Rejected.
  The reason to have the ABC is the hooks; with only `build_tools` left,
  it degenerates into "pass a `list[Tool]`." Do that directly.

- **Teach the runtime to copy `WorkerOutput.artifacts` through the
  boundary.** Rejected for the same reason as the column: wrong channel.
  Files are not cheap to copy inline through Inngest event payloads;
  `run_resources` blob storage is the right place.

- **`get_all_files_for_task(size_cap=N)`.** Discussed on the design
  thread; rejected (user preference). `list_resources()` + selective
  `read_resource()` remain available for callers with specific size
  concerns.

- **Delete `WorkerOutput.artifacts` in this PR.** Rejected — it is on
  the public Worker return contract. Ripples into every subclass +
  test. Do it as a follow-up once built-ins stop using it.

- **Add a `setup_spec: SWEBenchSetupSpec` kwarg to
  `BaseSandboxManager.create()`.** Rejected. The shape of that spec
  differs per benchmark (SWE-Bench wants `install_repo_script` +
  `setup_env_script`; GDPEval wants `pip install <pkgs>`; MiniF2F wants
  nothing), so the kwarg would either have to be a `dict[str, Any]`
  catch-all or a discriminated union the base class knows about. Both
  versions leak benchmark-specific knowledge into `BaseSandboxManager`,
  which defeats the point. The `_install_dependencies` hook already
  solves this — each manager knows how to fetch its own per-task data.

- **Pass `BenchmarkTask` (or `task_payload`) through the Inngest
  `SandboxSetupRequest` event payload.** Rejected. The sandbox-setup step
  already has `task_id`; broadcasting the full payload inside the event
  duplicates data that already lives in Postgres and encourages workers /
  managers to read from the event blob rather than the canonical
  `experiment_definition_tasks` row. The data-layer lookup via
  `queries.task_executions.get_task_payload` keeps the event payload
  narrow and puts the read next to the sibling per-task query methods.

- **Put the payload JOIN helper on `BaseSandboxManager` itself (e.g. as
  `_load_task_payload`).** Rejected. The JOIN is a data-layer concern and
  belongs in `TaskExecutionsQueries`, next to `get_by_task` /
  `get_latest_by_task`. Sandbox managers should consume the data layer,
  not re-implement it. This also keeps the method testable in isolation
  via the existing queries-layer test fixtures.

- **Keep the current nullable-with-default `ReActWorker.__init__` shape
  (`tools = None`, `system_prompt = None`, `max_iterations = 10`).**
  Rejected. Defaults on a concrete worker `__init__` hide sizing
  decisions — a new benchmark silently inherits `max_iterations=10`
  until someone notices runs are cutting short, and factory closures
  read as "pass the few things I care about" rather than "declare my
  full sizing contract." Making all kwargs required pushes every
  decision up to the registry (where it belongs) and lets `ty` flag
  "forgot to pick a value" at the type level.

## Open questions

All three resolved during plan execution on branch
`feature/real-llm-harness-infra` (PR #27). The rest had been absorbed
into the proposal above (MiniF2F proof filename is
`final_solution.lean`; `get_task_payload` takes `session: Session`
mirroring its siblings; the base `Worker` class also drops its
`model` default).

1. **Non-benchmark-specific workers' kwarg shape.** **Resolved —
   option (b).** Every bare worker class
   (`StubWorker`, `TrainingStubWorker`, `SmokeTestWorker`,
   `ManagerResearcherWorker`, `StubResearchRubricsWorker`,
   `CanonicalSmokeWorker`, `ResearchRubricsManagerWorker`,
   `ResearchRubricsResearcherWorker`) is wrapped in the `_plain(cls)`
   factory closure in `ergon_builtins/registry_core.py` and re-used
   from `registry_data.py`. The closure accepts the registry's
   uniform `(name, model, task_id, sandbox_id)` signature and
   forwards only `(name, model)` to the underlying `__init__`.
   Subclasses never learn about `task_id` / `sandbox_id`.

2. **`ensure_sandbox()` idempotence check.** **Resolved.** Regression
   test landed at
   `tests/unit/sandbox/test_ensure_sandbox_idempotence.py` — patches
   `AsyncSandbox`, calls `ensure_sandbox()` three times, and asserts
   `_install_dependencies` runs exactly once.

3. **Do we need a `read_resource_text` convenience?** **Resolved —
   no.** `CriterionRuntime.read_resource` returns `bytes`; criteria
   decode at the call site (e.g.
   `raw.decode("utf-8", errors="replace")` in
   `ProofVerificationCriterion._extract_proof`). The Protocol stays
   at 12 methods with the new `get_all_files_for_task` addition.

## On acceptance

- [ ] Move `docs/rfcs/active/2026-04-22-worker-interface-and-artifact-routing.md`
      → `docs/rfcs/accepted/`.
- [ ] Update `docs/architecture/01_public_api.md` — Worker contract +
      CriterionRuntime surface.
- [ ] Update `docs/architecture/06_builtins.md` — remove adapter section,
      add anti-patterns.
- [ ] Update `docs/architecture/cross_cutting/artifacts.md` —
      non-durability invariant for `WorkerOutput.artifacts`.
- [ ] Link the implementation plan in
      `docs/superpowers/plans/` when written.
- [ ] After PR #27 merges, track the follow-up to fully delete
      `WorkerOutput.artifacts` once no in-tree worker writes to it.
