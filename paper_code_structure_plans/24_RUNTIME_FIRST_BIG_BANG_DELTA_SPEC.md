# Runtime-First Big-Bang Delta Spec

## Goal
This is the code-first version of the runtime-first proposal.

It assumes we are willing to do a **real breaking change** rather than a long compatibility migration. The purpose of this note is to show:

- proposed public API deltas
- new type signatures
- module-level changes
- what gets deleted
- what runtime requests look like
- how library usage changes
- how CLI usage changes

This is intentionally more "what code should exist" and less "why architecture matters."

## Core Decision
The core decision is:

**stop putting live worker instances inside the persisted workflow model**

and replace that with:

- serializable `WorkerSpec`
- serializable `WorkflowSpec`
- explicit `submit_*` APIs for runtime-backed execution
- explicit `execute_local` for in-process execution

The runtime becomes the only place where `WorkerRuntime` instances are materialized for runtime-backed execution.

## Breaking Changes At A Glance
### Current shape
Today the public shape is roughly:

```python
worker = ReActWorker(model="gpt-4o", config=...)

task = Task(
    name="Research",
    description="...",
    assigned_to=worker,
    children=[...],
)

result = await execute_task(task)
```

This is elegant at the call site, but it mixes:

- authoring
- runtime submission
- live worker identity
- persistence
- orchestration

### Proposed shape
The proposed shape is:

```python
worker = ReActWorkerSpec(
    key="researcher",
    model="gpt-4o",
    config=ReActWorkerConfig(...),
)

workflow = WorkflowSpec(
    name="Competitive Analysis",
    tasks=[
        TaskSpec(
            key="research",
            name="Research",
            description="...",
            assigned_to="researcher",
        ),
    ],
    workers=[worker],
)
```

Then execution becomes explicit:

```python
result = await execute_local(workflow)
```

or:

```python
run = await submit_workflow(workflow, target="local-runtime")
```

This is the single biggest conceptual delta in the redesign.

## Proposed Public API

### 1. Authoring Models
Replace the current "task contains live worker instance" model with serializable authoring specs.

#### New `TaskSpec`
```python
class TaskSpec(BaseModel):
    key: str
    name: str
    description: str
    assigned_to: str
    depends_on: list[str] = Field(default_factory=list)
    children: list["TaskSpec"] = Field(default_factory=list)
    resources: list[ResourceSpec] = Field(default_factory=list)
    evaluator: EvaluatorSpec | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
```

#### New `WorkflowSpec`
```python
class WorkflowSpec(BaseModel):
    name: str
    description: str | None = None
    tasks: list[TaskSpec]
    workers: list["WorkerSpec"]
    benchmark_name: str = "custom"
    metadata: dict[str, Any] = Field(default_factory=dict)
```

#### New `ResourceSpec`
```python
class ResourceSpec(BaseModel):
    key: str | None = None
    name: str
    path: str | None = None
    content: str | bytes | None = None
    url: str | None = None
    mime_type: str | None = None
```

### 2. Worker Definitions
Split worker definition into:

- serializable worker spec
- runtime worker implementation
- factory for reconstruction

#### New `WorkerSpec`
```python
class WorkerSpec(BaseModel):
    key: str
    kind: str
    model: str
    config: dict[str, Any] = Field(default_factory=dict)
```

#### Benchmark-specific worker spec
```python
class ReActWorkerSpec(WorkerSpec):
    kind: Literal["react_worker"] = "react_worker"
    config: ReActWorkerConfig
```

#### Runtime interface
```python
class WorkerRuntime(Protocol):
    key: str
    model: str

    async def execute(
        self,
        task: RuntimeTask,
        context: RuntimeWorkerContext,
    ) -> RuntimeWorkerResult:
        ...
```

#### Factory
```python
class WorkerFactory(Protocol):
    def build(self, spec: WorkerSpec) -> WorkerRuntime:
        ...
```

This is the key split:

- `WorkerSpec` crosses process boundaries
- `WorkerRuntime` does not

### 3. Execution APIs
Replace one ambiguous top-level execution API with two explicit ones.

#### Local execution
```python
async def execute_local(
    workflow: WorkflowSpec,
    *,
    timeout_seconds: float | None = None,
    max_concurrent_tasks: int = 10,
) -> ExecutionResult:
    ...
```

#### Runtime submission
```python
async def submit_workflow(
    workflow: WorkflowSpec,
    *,
    target: str = "local-runtime",
    cohort_name: str | None = None,
    timeout_seconds: float | None = None,
) -> SubmittedRun:
    ...
```

#### Runtime client
```python
class ArcaneClient:
    def __init__(self, target: str = "local-runtime"): ...

    async def submit(self, workflow: WorkflowSpec, *, cohort_name: str | None = None) -> SubmittedRun:
        ...

    async def get_run(self, run_id: UUID) -> RunSnapshotDto:
        ...

    async def wait(self, run_id: UUID, *, timeout_seconds: float | None = None) -> ExecutionResult:
        ...
```

### 4. Runtime Request Models
These become the only legal handoff into the runtime.

```python
class WorkflowSubmissionRequest(BaseModel):
    workflow: WorkflowSpec
    dispatch: DispatchSpec


class DispatchSpec(BaseModel):
    cohort_name: str | None = None
    max_concurrent_tasks: int = 10
    timeout_seconds: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
```

## Proposed Usage

### Before
```python
from h_arcane import Task, execute_task
from h_arcane.benchmarks.common.workers.react_worker import ReActWorker

worker = ReActWorker(model="gpt-4o", config=config)

workflow = Task(
    name="Competitive Analysis",
    description="Research and write a brief",
    assigned_to=worker,
    children=[
        Task(
            name="Research",
            description="Find the latest competitor pricing",
            assigned_to=worker,
        )
    ],
)

result = await execute_task(workflow)
```

### After: local mode
```python
from h_arcane import WorkflowSpec, TaskSpec, execute_local
from h_arcane.workers import ReActWorkerSpec, ReActWorkerConfig

workflow = WorkflowSpec(
    name="Competitive Analysis",
    workers=[
        ReActWorkerSpec(
            key="researcher",
            model="gpt-4o",
            config=ReActWorkerConfig(
                system_prompt="You are a research worker",
                max_questions=10,
            ),
        )
    ],
    tasks=[
        TaskSpec(
            key="research",
            name="Research",
            description="Find the latest competitor pricing",
            assigned_to="researcher",
        )
    ],
)

result = await execute_local(workflow)
```

### After: runtime mode
```python
from h_arcane import WorkflowSpec, TaskSpec, submit_workflow
from h_arcane.workers import ReActWorkerSpec, ReActWorkerConfig

workflow = WorkflowSpec(
    name="Competitive Analysis",
    workers=[
        ReActWorkerSpec(
            key="researcher",
            model="gpt-4o",
            config=ReActWorkerConfig(
                system_prompt="You are a research worker",
                max_questions=10,
            ),
        )
    ],
    tasks=[
        TaskSpec(
            key="research",
            name="Research",
            description="Find the latest competitor pricing",
            assigned_to="researcher",
        )
    ],
)

run = await submit_workflow(
    workflow,
    target="local-runtime",
    cohort_name="pricing-sanity-check",
)
```

## Proposed CLI Delta

### Current CLI style
Today the CLI is still partially shaped around setup plus benchmark flows, with runtime assumptions hidden inside those flows.

### Proposed CLI shape
Make the CLI explicitly control-plane oriented.

```bash
magym dev up
magym dev down
magym dev doctor

magym run submit workflow.yaml --target local-runtime
magym run status <run-id>
magym run watch <run-id>
magym run inspect <run-id>

magym benchmark seed minif2f --limit 10
magym benchmark submit minif2f --experiment-id ... --target local-runtime
magym cohort list
magym cohort inspect <cohort-name>
```

### Proposed CLI parser deltas
- Keep `dev up/down/doctor`
- Replace benchmark `run` with benchmark `submit`
- Add generic `run submit`
- Add `run wait/watch/status/inspect`
- Remove any CLI path that assumes local Python worker instances are execution-time truth for runtime-backed runs

## Proposed Internal Module Deltas

### Replace `core/task.py`
Current:

- `Task` stores live `BaseWorker` instances
- serialization strips worker objects down only for display/persistence

Proposed:

- `TaskSpec`
- `WorkflowSpec`
- `ResourceSpec`
- no live runtime worker objects embedded in authoring models

### Replace `core/worker.py`
Current:

- `BaseWorker`
- `WorkerContext`
- `WorkerResult`
- worker instance is both authoring-time and runtime-time identity

Proposed split:

```python
h_arcane/core/workers/specs.py
h_arcane/core/workers/runtime.py
h_arcane/core/workers/factory.py
h_arcane/core/workers/context.py
```

Suggested responsibilities:

- `specs.py`: `WorkerSpec`, benchmark-specific spec models
- `runtime.py`: `WorkerRuntime`, `RuntimeWorkerResult`
- `factory.py`: reconstruction logic
- `context.py`: typed runtime execution context

### Replace `core/runner.py`
Current:

- `execute_task(task, ...)`
- persists workflow
- stores worker registry
- triggers runtime orchestration
- waits for completion

Proposed:

```python
async def execute_local(workflow: WorkflowSpec, ...) -> ExecutionResult: ...
async def submit_workflow(workflow: WorkflowSpec, ...) -> SubmittedRun: ...
```

Optional:

```python
async def wait_for_run(run_id: UUID, ...) -> ExecutionResult: ...
```

### Delete `core/_internal/task/worker_context.py`
Delete entirely from runtime-backed flow.

Current responsibility:

- process-local task_id -> worker mapping

Proposed replacement:

- persisted `WorkerSpec`
- runtime `WorkerFactory`

### Rewrite `core/_internal/task/inngest_functions/benchmark_run_start.py`
Current:

- reconstructs `ReActWorker`
- stores worker in in-memory registry
- persists task tree

Proposed:

- build `WorkflowSubmissionRequest`
- persist `WorkflowSpec`
- persist `DispatchSpec`
- emit runtime start event
- no in-memory worker registration

Pseudo-shape:

```python
async def benchmark_run_start(ctx: inngest.Context) -> BenchmarkRunResult:
    payload = BenchmarkLaunchRequest.model_validate(ctx.event.data)
    workflow = build_benchmark_workflow_spec(payload)
    run = persist_submission(workflow=workflow, dispatch=payload.dispatch)
    await emit_workflow_started(run.id)
    return BenchmarkRunResult(...)
```

## Proposed Persistence Delta

### Current persistence model
Current persistence is oriented around:

- task tree JSON
- run metadata
- resource records
- agent mappings
- dynamic runtime reconstruction hacks

### Proposed persistence additions
Persist the submitted spec directly.

```python
class Run(SQLModel, table=True):
    ...
    submission_spec_json: dict = Field(default_factory=dict, sa_column=Column(JSON))
    dispatch_spec_json: dict = Field(default_factory=dict, sa_column=Column(JSON))
```

Optional normalization if you want cleaner querying:

```python
class SubmittedWorkflow(SQLModel, table=True):
    id: UUID
    run_id: UUID
    workflow_spec_json: dict
    created_at: datetime
```

### Proposed agent config delta
Current `AgentConfig` is partly compensating for the runtime/object split.

Under the new model:

- `AgentConfig` can remain as the runtime snapshot of materialized execution config
- but it should be derived from `WorkerSpec`
- not from a live worker instance created in another process

## Proposed Action Delta
While doing the big bang, fix action lineage at the same time.

### Current
```python
class Action(SQLModel, table=True):
    run_id: UUID
    agent_id: UUID | None
    ...
```

### Proposed
```python
class Action(SQLModel, table=True):
    run_id: UUID
    task_id: UUID
    task_execution_id: UUID
    agent_id: UUID | None
    action_num: int
    action_type: str
    input: str
    output: str | None
    error: dict | None
    started_at: datetime
    completed_at: datetime | None
    duration_ms: int | None
```

This lets `runs.py` stop guessing ownership.

## Proposed Runtime Execution Delta

### Current shape
Today runtime execution is approximately:

1. look up worker from memory
2. build toolkit/sandbox
3. invoke worker
4. parse transcript into actions
5. persist actions

### Proposed shape
Runtime execution should be:

1. load run + persisted `WorkflowSpec`
2. resolve the current task by task key/id
3. load the assigned `WorkerSpec`
4. build runtime worker via `WorkerFactory`
5. build typed runtime context
6. execute worker
7. record actions with explicit task/task_execution lineage
8. persist outputs/events/snapshots

Pseudo-signature:

```python
async def execute_task_attempt(
    run_id: UUID,
    task_id: UUID,
    task_execution_id: UUID,
) -> WorkerAttemptResult:
    ...
```

## Proposed Local Execution Delta
Local mode should still exist, but it should stop shaping runtime architecture.

### Proposed local executor shape
```python
async def execute_local(
    workflow: WorkflowSpec,
    *,
    timeout_seconds: float | None = None,
    max_concurrent_tasks: int = 10,
) -> ExecutionResult:
    ...
```

Implementation note:

- local mode may still instantiate workers directly from `WorkerSpec`
- local mode may skip DB/Inngest entirely, or may use an in-memory persistence adapter
- local mode should not require Docker

This preserves research ergonomics without contaminating the runtime path.

## Proposed Benchmark Delta
Benchmarks should stop constructing live runtime workers as the primary abstraction.

### Current benchmark pattern
```python
worker = ReActWorker(model=payload.model, config=worker_config)
task = workflow_factory(worker)
```

### Proposed benchmark pattern
```python
worker = ReActWorkerSpec(
    key="default_worker",
    model=payload.model,
    config=worker_config,
)
workflow = workflow_factory(worker_key="default_worker")
```

or:

```python
workflow = BenchmarkWorkflowFactory(...).build(worker_spec=worker)
```

The key point is:

- benchmark factories produce `WorkflowSpec`
- not task trees with embedded live runtime workers

## Proposed File/Module Additions
Suggested new modules:

```text
h_arcane/core/specs/workflow.py
h_arcane/core/specs/task.py
h_arcane/core/specs/resource.py
h_arcane/core/specs/dispatch.py
h_arcane/core/specs/workers.py

h_arcane/core/runtime/client.py
h_arcane/core/runtime/submission.py
h_arcane/core/runtime/factory.py
h_arcane/core/runtime/executor.py
h_arcane/core/runtime/context.py
h_arcane/core/runtime/local_executor.py
```

## Proposed File/Module Deletions Or Major Shrinks
Likely remove or heavily rewrite:

```text
h_arcane/core/_internal/task/worker_context.py
h_arcane/core/runner.py
h_arcane/core/task.py
h_arcane/core/worker.py
h_arcane/core/_internal/task/inngest_functions/benchmark_run_start.py
```

## Proposed Compatibility Stance
Because this is a big-bang plan, I would not aim for a wide compatibility layer.

I would do:

- one intentional breaking release
- one clear before/after example in docs
- one codemod-style migration guide if needed

I would not try to keep:

- `Task.assigned_to = BaseWorker`
- runtime-backed `execute_task(task)` semantics
- process-local worker recovery hacks

Those are the exact things we are trying to remove.

## Recommended Final Public Surface
If this redesign lands cleanly, I would want the user-facing imports to look something like:

```python
from h_arcane import (
    WorkflowSpec,
    TaskSpec,
    ResourceSpec,
    ExecutionResult,
    SubmittedRun,
    execute_local,
    submit_workflow,
    ArcaneClient,
)

from h_arcane.workers import (
    WorkerSpec,
    ReActWorkerSpec,
    ReActWorkerConfig,
)
```

That is much more honest about the system shape:

- specs for authoring
- explicit local execution
- explicit runtime submission
- explicit client for runtime interaction

## Non-Goals
This proposal does **not** try to:

- preserve the current worker-in-task authoring model
- keep one API that hides local and runtime differences
- preserve in-memory worker continuity across processes

Those are deliberate casualties of the redesign.

## Short Version
If doing this as a big bang, the actual delta is:

1. Replace live worker instances in `Task` with serializable worker references.
2. Introduce `WorkflowSpec` / `TaskSpec` / `WorkerSpec`.
3. Split `execute_task()` into `execute_local()` and `submit_workflow()`.
4. Make runtime execution reconstruct from persisted specs.
5. Delete the process-local worker registry from runtime-backed execution.
6. Fix action lineage while doing the rewrite.
7. Make the CLI a control plane, not a pseudo-runtime host.

That is the code-shaped version of the runtime-first proposal.
