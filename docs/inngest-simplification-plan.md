# Inngest Function Simplification Plan

## Overview

This document outlines a plan to reduce complexity in our Inngest functions through:

1. **Step reduction** - Remove unnecessary `step.run` calls for pure reads/transforms
2. **Type safety** - Replace `dict` / `list[dict]` returns with typed Pydantic models
3. **Function extraction** - Break monolithic functions into smaller invokable functions
4. **Control flow** - Simplify branching and error handling

### Memoization Guidelines

**Safe to inline** (no `step.run` needed):
- DB reads (idempotent)
- Pure transformations (no side effects)
- Cheap operations

**Must wrap in `step.run`**:
- External API calls (sandbox, LLM)
- DB writes (non-idempotent)
- Event emissions (avoid duplicates)
- Expensive operations (worth caching)

---

## Architectural Improvements

### 1. Typed Return Values

**Problem:** Most functions return `dict` which loses type safety.

**Solution:** Define result models for each function.

```python
# Before
async def task_execute(ctx: inngest.Context) -> dict:
    ...
    return {"run_id": str(run_id), "success": True}

# After
class TaskExecuteResult(BaseModel):
    run_id: UUID
    task_id: UUID
    execution_id: UUID | None
    success: bool
    skipped: bool = False
    skip_reason: str | None = None
    outputs_count: int = 0
    questions_asked: int = 0

@inngest_client.create_function(..., output_type=TaskExecuteResult)
async def task_execute(ctx: inngest.Context) -> TaskExecuteResult:
    ...
```

### 2. Extract Reusable Child Functions

**Problem:** `task_execute` is ~375 lines doing sandbox setup, worker execution, and result persistence all in one place.

**Solution:** Extract into invokable child functions:

```
task_execute (orchestrator)
├── step.invoke(setup_sandbox_fn)      # New function
├── step.invoke(execute_worker_fn)     # New function  
└── step.invoke(persist_results_fn)    # New function
```

Benefits:
- Each function has single responsibility
- Typed inputs/outputs via events
- Reusable across different workflows
- Better error isolation

### 3. Replace `list[dict]` with Typed Lists

**Problem:** Several steps return `list[dict]` requiring manual deserialization.

```python
# Current - loses type info
async def get_evaluators() -> list[dict]:
    evaluators = queries.task_evaluators.get_by_task(run_id, task_id)
    return [e.model_dump(mode="json") for e in evaluators]

evaluator_dicts = await ctx.step.run("get-evaluators", get_evaluators)
# Now we have list[dict] and need to manually access fields
```

**Solution:** Use typed wrapper models:

```python
class EvaluatorList(BaseModel):
    items: list[TaskEvaluator]

async def get_evaluators() -> EvaluatorList:
    evaluators = queries.task_evaluators.get_by_task(run_id, task_id)
    return EvaluatorList(items=evaluators)

result = await ctx.step.run("get-evaluators", get_evaluators, output_type=EvaluatorList)
# result.items is list[TaskEvaluator] with full type safety
```

### 4. Simplify Control Flow with Early Returns

**Problem:** `task_execute` has a 250-line try/except block.

**Solution:** Use early returns and smaller try blocks:

```python
# Before - giant try block
try:
    # 200 lines of setup
    # execution
    # persistence
except Exception as exc:
    # handle failure

# After - targeted error handling
execution = await create_and_start_execution(...)
if not execution:
    return TaskExecuteResult(success=False, error="Failed to create execution")

try:
    worker_result = await ctx.step.invoke("execute-worker", execute_worker_fn, ...)
except Exception as exc:
    await handle_worker_failure(execution.id, exc)
    raise

await persist_results(...)
```

---

## Function-by-Function Analysis

---

### 1. `workflow_start.py`

**Current:** 6 steps, returns `dict`  
**Proposed:** 4 steps, returns `WorkflowStartResult`

#### Step Changes

| Step | Verdict | Rationale |
|------|---------|-----------|
| `load-experiment` | **REMOVE** | Inline read |
| `create-dependencies` | **COMBINE** | Merge into `initialize-dag` |
| `create-evaluators` | **COMBINE** | Merge into `initialize-dag` |
| `mark-executing` | KEEP | |
| `get-initial-ready-tasks` | KEEP | |
| `emit-task-ready-{id}` | KEEP | |

#### Type Safety

```python
# New result type
class WorkflowStartResult(BaseModel):
    run_id: UUID
    dependencies_created: int
    evaluators_created: int
    initial_ready_tasks: int

# Combined init result (replaces 2 contracts)
class DagInitResult(BaseModel):
    dependency_count: int
    evaluator_count: int

# Function signature
@inngest_client.create_function(..., output_type=WorkflowStartResult)
async def workflow_start(ctx: inngest.Context) -> WorkflowStartResult:
```

#### Contracts to Delete
- `DependencyCreationResult`
- `EvaluatorCreationResult`

---

### 2. `task_execute.py` (MAJOR REFACTOR)

**Current:** 15+ steps, returns `dict`, 375 lines  
**Proposed:** 5 steps + child invocations, returns `TaskExecuteResult`, ~150 lines

#### Architecture: Extract Child Functions

The current function does too much. Extract into focused, invokable child functions:

```
task_execute (orchestrator ~100 lines)
│
├─ inline: load context, parse tree, check leaf
├─ step: create-running-execution (DB writes)
├─ step.invoke: setup_sandbox_fn → SandboxReadyResult
├─ step.invoke: execute_worker_fn → WorkerExecutionResult  
├─ step.invoke: persist_outputs_fn → PersistOutputsResult
└─ step: emit-completed/failed (event)
```

#### New Child Functions

**1. `setup_sandbox_fn`** (new file: `inngest_functions/sandbox_setup.py`)
```python
class SandboxSetupEvent(BaseModel):
    run_id: UUID
    experiment_id: UUID
    task_id: UUID
    benchmark_name: str
    skills_dir: str | None

class SandboxReadyResult(BaseModel):
    sandbox_id: str
    output_dir: str

@inngest_client.create_function(
    fn_id="setup-sandbox",
    trigger=inngest.TriggerEvent(event=SandboxSetupEvent.name),
    output_type=SandboxReadyResult,
)
async def setup_sandbox_fn(ctx: inngest.Context) -> SandboxReadyResult:
    # Create sandbox, save ID to run, return result
```

**2. `execute_worker_fn`** (new file: `inngest_functions/worker_execute.py`)
```python
class WorkerExecuteEvent(BaseModel):
    run_id: UUID
    task_id: UUID
    execution_id: UUID
    sandbox_id: str
    task_description: str
    input_resources: list[ResourceRecord]
    worker_model: str
    benchmark_name: str

class WorkerExecuteResult(BaseModel):
    success: bool
    output_text: str | None
    questions_asked: int

@inngest_client.create_function(
    fn_id="execute-worker",
    trigger=inngest.TriggerEvent(event=WorkerExecuteEvent.name),
    output_type=WorkerExecuteResult,
)
async def execute_worker_fn(ctx: inngest.Context) -> WorkerExecuteResult:
    # Setup toolkit, execute worker, return result
```

**3. `persist_outputs_fn`** (new file: `inngest_functions/persist_outputs.py`)
```python
class PersistOutputsEvent(BaseModel):
    run_id: UUID
    task_id: UUID
    execution_id: UUID
    sandbox_id: str
    output_dir: str

class PersistOutputsResult(BaseModel):
    output_resource_ids: list[UUID]
    outputs_count: int

@inngest_client.create_function(
    fn_id="persist-outputs",
    trigger=inngest.TriggerEvent(event=PersistOutputsEvent.name),
    output_type=PersistOutputsResult,
)
async def persist_outputs_fn(ctx: inngest.Context) -> PersistOutputsResult:
    # Download from sandbox, register resources
```

#### Simplified `task_execute`

```python
class TaskExecuteResult(BaseModel):
    run_id: UUID
    task_id: UUID
    execution_id: UUID | None = None
    success: bool
    skipped: bool = False
    skip_reason: str | None = None
    outputs_count: int = 0
    questions_asked: int = 0
    error: str | None = None

@inngest_client.create_function(..., output_type=TaskExecuteResult)
async def task_execute(ctx: inngest.Context) -> TaskExecuteResult:
    payload = TaskReadyEvent.model_validate(ctx.event.data)
    
    # Inline reads (no step.run)
    run = queries.runs.get(payload.run_id)
    experiment = queries.experiments.get(payload.experiment_id)
    tree = parse_task_tree(experiment.task_tree)
    task_node = tree.find_by_id(str(payload.task_id))
    
    # Early return for composite tasks
    if not task_node.is_leaf:
        return TaskExecuteResult(
            run_id=payload.run_id,
            task_id=payload.task_id,
            success=True,
            skipped=True,
            skip_reason="composite_task",
        )
    
    # Create execution record (single step for both create + mark running)
    execution = await ctx.step.run("create-execution", create_running_execution)
    
    try:
        # Invoke child functions
        sandbox = await ctx.step.invoke("setup-sandbox", setup_sandbox_fn, data=...)
        worker_result = await ctx.step.invoke("execute-worker", execute_worker_fn, data=...)
        persist_result = await ctx.step.invoke("persist-outputs", persist_outputs_fn, data=...)
        
        # Complete and emit
        await ctx.step.run("complete-and-emit", complete_and_emit_success)
        
        return TaskExecuteResult(success=True, ...)
        
    except Exception as exc:
        await ctx.step.run("fail-and-emit", fail_and_emit_error)
        raise
```

#### Contracts to Delete
- `LoadContextResult`
- `PrepareExecutionResult`
- `PersistResult`
- `SandboxSetupResult` (replaced by `SandboxReadyResult` on child fn)

---

### 3. `task_propagate.py`

**Current:** 4-6 steps, returns `dict`  
**Proposed:** 2-3 steps, returns `TaskPropagateResult`

#### Step Changes

| Step | Verdict | Rationale |
|------|---------|-----------|
| `propagate` | KEEP | |
| `emit-ready-{id}` | KEEP | |
| `check-workflow-status` | **REMOVE** | Inline reads |
| `emit-workflow-completed` | KEEP | |
| `emit-workflow-failed` | KEEP | |

#### Type Safety

```python
class TaskPropagateResult(BaseModel):
    run_id: UUID
    task_id: UUID
    newly_ready_tasks: int
    workflow_complete: bool
    workflow_failed: bool

@inngest_client.create_function(..., output_type=TaskPropagateResult)
async def task_propagate(ctx: inngest.Context) -> TaskPropagateResult:
```

#### Contracts to Delete
- `WorkflowStatusResult`

---

### 4. `workflow_complete.py`

**Current:** 3 steps, returns `dict`  
**Proposed:** 2 steps, returns `WorkflowCompleteResult`

#### Step Changes

| Step | Verdict | Rationale |
|------|---------|-----------|
| `mark-completed` | **COMBINE** | Into `finalize-run` |
| `aggregate-scores` | **COMBINE** | Into `finalize-run` |
| `emit-cleanup` | KEEP | |

#### Type Safety

```python
class WorkflowCompleteResult(BaseModel):
    run_id: UUID
    status: Literal["completed"]
    final_score: float | None
    normalized_score: float | None
    evaluators_count: int

@inngest_client.create_function(..., output_type=WorkflowCompleteResult)
async def workflow_complete(ctx: inngest.Context) -> WorkflowCompleteResult:
```

---

### 5. `workflow_failed.py`

**Current:** 2 steps, returns `dict`  
**Proposed:** 1 step, returns `WorkflowFailedResult`

#### Step Changes

| Step | Verdict | Rationale |
|------|---------|-----------|
| `mark-failed` | **COMBINE** | Into `fail-and-cleanup` |
| `emit-cleanup` | **COMBINE** | Into `fail-and-cleanup` |

#### Type Safety

```python
class WorkflowFailedResult(BaseModel):
    run_id: UUID
    status: Literal["failed"]
    error: str

@inngest_client.create_function(..., output_type=WorkflowFailedResult)
async def workflow_failed(ctx: inngest.Context) -> WorkflowFailedResult:
```

---

### 6. `evaluation.py` (`check_and_run_evaluators`)

**Current:** 5+ steps, returns `dict`, uses `list[dict]`  
**Proposed:** 1 step + invokes, returns `EvaluatorsResult`, fully typed

#### Architecture Change

Currently converts `TaskEvaluator` → `dict` → manual field access. Fix with typed wrapper:

```python
class TaskEvaluatorList(BaseModel):
    """Wrapper to preserve type through step serialization."""
    items: list[TaskEvaluator]

class TaskEvaluationData(BaseModel):
    """Typed container for task evaluation context."""
    task_input: str
    agent_reasoning: str
    outputs: list[ResourceRecord]
```

#### Step Changes

| Step | Verdict | Rationale |
|------|---------|-----------|
| `get-evaluators` | **REMOVE** | Inline read |
| `load-task-data` | **REMOVE** | Inline reads |
| `mark-running-{id}` | **REMOVE** | Move into evaluate step |
| `evaluate-{id}` (invoke) | KEEP | |
| `mark-completed-{id}` | **REMOVE** | Move into evaluate step |

#### Type Safety

```python
class EvaluatorsResult(BaseModel):
    task_id: UUID
    evaluators_found: int
    evaluators_run: int
    scores: list[float]

@inngest_client.create_function(..., output_type=EvaluatorsResult)
async def check_and_run_evaluators(ctx: inngest.Context) -> EvaluatorsResult:
```

#### Contracts to Delete
- Local `EvaluatorsRunResult`

---

### 7. `evaluate_task_run.py`

**Current:** 0 steps, returns `TaskEvaluationResult`  
**Proposed:** No changes - already optimal

---

### 8. `evaluate_criterion_fn` (criterion.py)

**Current:** 1 step, returns `CriterionResult`  
**Proposed:** No changes - already optimal

---

### 9. `run_cleanup.py`

**Current:** 2 steps, returns `dict`  
**Proposed:** 1 step, returns `RunCleanupResult`

#### Step Changes

| Step | Verdict | Rationale |
|------|---------|-----------|
| `terminate-sandbox` | KEEP | |
| `verify-run-status` | **COMBINE** | Inline into terminate step |

#### Type Safety

```python
class RunCleanupResult(BaseModel):
    run_id: UUID
    status: str
    sandbox_terminated: bool
    sandbox_id: str | None = None

@inngest_client.create_function(..., output_type=RunCleanupResult)
async def run_cleanup(ctx: inngest.Context) -> RunCleanupResult:
```

#### Contracts to Delete
- `VerifyRunStatusResult`

---

## Summary

### Step Reduction

| File | Current | Proposed | Reduction |
|------|---------|----------|-----------|
| `workflow_start.py` | 6 | 4 | -2 |
| `task_execute.py` | 15+ | 5 + invokes | -10+ |
| `task_propagate.py` | 4-6 | 2-3 | -2 |
| `workflow_complete.py` | 3 | 2 | -1 |
| `workflow_failed.py` | 2 | 1 | -1 |
| `evaluation.py` | 5+ | 1 + invokes | -4+ |
| `run_cleanup.py` | 2 | 1 | -1 |
| **Total** | **~37** | **~16** | **~55%** |

### Type Safety Improvements

| Change | Count |
|--------|-------|
| Functions returning `dict` → typed model | 7 |
| `list[dict]` → typed wrapper | 2 |
| New typed result models | 9 |

### New Files (Child Functions)

| File | Purpose |
|------|---------|
| `inngest_functions/sandbox_setup.py` | Extracted sandbox creation |
| `inngest_functions/worker_execute.py` | Extracted worker execution |
| `inngest_functions/persist_outputs.py` | Extracted output persistence |

### Contracts to Delete

From `step_outputs.py`:
- `LoadContextResult`
- `PrepareExecutionResult`
- `PersistResult`
- `WorkflowStatusResult`
- `SandboxSetupResult`

From `infrastructure/step_outputs.py`:
- `VerifyRunStatusResult`

From `evaluation.py`:
- `EvaluatorsRunResult`

**Total: 7 contracts deleted**

---

## Implementation Order

### Phase 1: Simple Functions (Low Risk)

1. **`workflow_failed.py`** - Simplest, combine 2 steps → 1, add typed result
2. **`task_propagate.py`** - Remove 1 step, add typed result
3. **`workflow_complete.py`** - Combine 2 steps, add typed result
4. **`run_cleanup.py`** - Combine 2 steps, add typed result

### Phase 2: Moderate Complexity

5. **`workflow_start.py`** - Combine steps, add typed result
6. **`evaluation.py`** - Remove inline steps, fix `list[dict]` typing

### Phase 3: Major Refactor

7. **Create child functions** - `sandbox_setup.py`, `worker_execute.py`, `persist_outputs.py`
8. **Refactor `task_execute.py`** - Use child invocations, add typed result

---

## Risks & Considerations

### Retry Behavior
Inlined reads will re-run on retry. This is safe for idempotent operations but changes observability (no separate step in Inngest UI).

### Debugging
Fewer steps means less granular tracing in Inngest dashboard. Consider adding structured logging for inlined operations.

### Error Boundaries
Combined steps mean errors in either operation fail the whole step. Ensure error messages clearly indicate which sub-operation failed.

### Testing
- Unit tests mocking step outputs will need updates
- Integration tests should still pass (behavior unchanged)

### Child Function Considerations
- Each `step.invoke` adds latency (new function invocation)
- But improves: isolation, reusability, testability
- Events between parent/child must be carefully typed

---

## File Structure

### Current Structure

```
h_arcane/core/_internal/
├── task/
│   ├── inngest_functions/
│   │   ├── __init__.py
│   │   ├── task_execute.py      # 375 lines, does too much
│   │   ├── task_propagate.py
│   │   ├── workflow_start.py
│   │   ├── workflow_complete.py
│   │   └── workflow_failed.py
│   ├── events.py                # Task/Workflow events
│   ├── step_outputs.py          # Step contracts (mixed concerns)
│   ├── schema.py                # TaskTreeNode
│   ├── persistence.py
│   ├── propagation.py
│   └── evaluation.py            # check_and_run_evaluators (misplaced?)
│
├── evaluation/
│   ├── inngest_functions/
│   │   ├── __init__.py
│   │   ├── task_run.py          # evaluate_task_run
│   │   └── criterion.py         # evaluate_criterion_fn
│   ├── events.py
│   └── ...
│
└── infrastructure/
    ├── inngest_functions/
    │   ├── __init__.py
    │   └── run_cleanup.py
    ├── events.py
    └── step_outputs.py          # TerminateSandboxResult, VerifyRunStatusResult
```

### Proposed Structure

```
h_arcane/core/_internal/
├── task/
│   ├── inngest_functions/
│   │   ├── __init__.py
│   │   │
│   │   │   # Orchestrators (trigger on external events)
│   │   ├── workflow_start.py        # WorkflowStartedEvent → WorkflowStartResult
│   │   ├── workflow_complete.py     # WorkflowCompletedEvent → WorkflowCompleteResult
│   │   ├── workflow_failed.py       # WorkflowFailedEvent → WorkflowFailedResult
│   │   ├── task_execute.py          # TaskReadyEvent → TaskExecuteResult (orchestrator)
│   │   ├── task_propagate.py        # TaskCompletedEvent → TaskPropagateResult
│   │   │
│   │   │   # Child functions (invoked by orchestrators)
│   │   ├── sandbox_setup.py         # SandboxSetupRequest → SandboxReadyResult
│   │   ├── worker_execute.py        # WorkerExecuteRequest → WorkerExecuteResult
│   │   └── persist_outputs.py       # PersistOutputsRequest → PersistOutputsResult
│   │
│   ├── events.py                    # External events (workflow/task lifecycle)
│   ├── requests.py                  # NEW: Child function request types
│   ├── results.py                   # NEW: All function result types
│   ├── schema.py                    # TaskTreeNode (domain model)
│   ├── persistence.py
│   └── propagation.py
│
├── evaluation/
│   ├── inngest_functions/
│   │   ├── __init__.py
│   │   ├── task_run.py
│   │   ├── criterion.py
│   │   └── check_evaluators.py      # MOVED from task/evaluation.py
│   ├── events.py
│   ├── results.py                   # NEW: EvaluatorsResult
│   └── ...
│
└── infrastructure/
    ├── inngest_functions/
    │   ├── __init__.py
    │   └── run_cleanup.py
    ├── events.py
    └── results.py                   # RENAMED from step_outputs.py
```

### File Responsibilities

#### `task/events.py` - External Events (unchanged)
```python
# Events triggered by external actions or other functions
class WorkflowStartedEvent(BaseModel):    # Triggers workflow_start
class TaskReadyEvent(BaseModel):          # Triggers task_execute
class TaskCompletedEvent(BaseModel):      # Triggers task_propagate, check_evaluators
class TaskFailedEvent(BaseModel):         # Triggers failure handling
class WorkflowCompletedEvent(BaseModel):  # Triggers workflow_complete
class WorkflowFailedEvent(BaseModel):     # Triggers workflow_failed
```

#### `task/requests.py` - Child Function Requests (NEW)
```python
# Request types for step.invoke() child functions
# These are "internal" events - only used parent→child

class SandboxSetupRequest(BaseModel):
    """Request to setup a sandbox for task execution."""
    name: ClassVar[str] = "task/sandbox-setup"
    
    run_id: UUID
    experiment_id: UUID
    task_id: UUID
    benchmark_name: str
    envs: dict[str, str] = {}


class WorkerExecuteRequest(BaseModel):
    """Request to execute a worker in an existing sandbox."""
    name: ClassVar[str] = "task/worker-execute"
    
    run_id: UUID
    task_id: UUID
    execution_id: UUID
    sandbox_id: str
    task_description: str
    input_resource_ids: list[UUID]  # IDs, not full objects (smaller payload)
    worker_model: str
    benchmark_name: str
    max_questions: int


class PersistOutputsRequest(BaseModel):
    """Request to download and persist outputs from sandbox."""
    name: ClassVar[str] = "task/persist-outputs"
    
    run_id: UUID
    task_id: UUID
    execution_id: UUID
    sandbox_id: str
    output_dir: str
    input_resource_ids: list[UUID]
```

#### `task/results.py` - Function Results (NEW)
```python
# Result types for all task inngest functions
# Used as output_type= in function decorators

from typing import Literal
from uuid import UUID
from pydantic import BaseModel


# === Workflow Results ===

class WorkflowStartResult(BaseModel):
    """Result of workflow_start function."""
    run_id: UUID
    dependencies_created: int
    evaluators_created: int
    initial_ready_tasks: int


class WorkflowCompleteResult(BaseModel):
    """Result of workflow_complete function."""
    run_id: UUID
    status: Literal["completed"] = "completed"
    final_score: float | None = None
    normalized_score: float | None = None
    evaluators_count: int = 0


class WorkflowFailedResult(BaseModel):
    """Result of workflow_failed function."""
    run_id: UUID
    status: Literal["failed"] = "failed"
    error: str


# === Task Orchestrator Results ===

class TaskExecuteResult(BaseModel):
    """Result of task_execute orchestrator function."""
    run_id: UUID
    task_id: UUID
    execution_id: UUID | None = None
    success: bool
    skipped: bool = False
    skip_reason: str | None = None
    outputs_count: int = 0
    questions_asked: int = 0
    error: str | None = None


class TaskPropagateResult(BaseModel):
    """Result of task_propagate function."""
    run_id: UUID
    task_id: UUID
    newly_ready_tasks: int
    workflow_complete: bool
    workflow_failed: bool


# === Child Function Results ===

class SandboxReadyResult(BaseModel):
    """Result of sandbox_setup child function."""
    sandbox_id: str
    output_dir: str


class WorkerExecuteResult(BaseModel):
    """Result of worker_execute child function."""
    success: bool
    output_text: str | None = None
    questions_asked: int = 0
    error: str | None = None


class PersistOutputsResult(BaseModel):
    """Result of persist_outputs child function."""
    output_resource_ids: list[UUID]
    outputs_count: int


# === Internal Step Results (keep minimal) ===

class DagInitResult(BaseModel):
    """Result of initialize-dag step (dependencies + evaluators)."""
    dependency_count: int
    evaluator_count: int


class ReadyTaskIdsResult(BaseModel):
    """Result of steps that identify ready tasks."""
    ready_task_ids: list[UUID]
```

#### `task/step_outputs.py` - DELETE
All contents moved to `task/results.py`. Delete this file.

#### `evaluation/results.py` (NEW)
```python
from uuid import UUID
from pydantic import BaseModel


class EvaluatorsResult(BaseModel):
    """Result of check_and_run_evaluators function."""
    task_id: UUID
    evaluators_found: int
    evaluators_run: int
    scores: list[float]
```

#### `infrastructure/results.py` (renamed from step_outputs.py)
```python
from uuid import UUID
from pydantic import BaseModel


class RunCleanupResult(BaseModel):
    """Result of run_cleanup function."""
    run_id: UUID
    status: str
    sandbox_terminated: bool
    sandbox_id: str | None = None


class TerminateSandboxResult(BaseModel):
    """Result of terminate-sandbox step."""
    success: bool
    run_id: str
    sandbox_terminated: bool = False
    sandbox_id: str | None = None
    message: str | None = None
    error: str | None = None

# DELETE: VerifyRunStatusResult (inlined)
```

### Summary of File Changes

| Action | File | Notes |
|--------|------|-------|
| CREATE | `task/requests.py` | Child function request types |
| CREATE | `task/results.py` | All task function results |
| DELETE | `task/step_outputs.py` | Replaced by results.py |
| CREATE | `task/inngest_functions/sandbox_setup.py` | New child function |
| CREATE | `task/inngest_functions/worker_execute.py` | New child function |
| CREATE | `task/inngest_functions/persist_outputs.py` | New child function |
| MOVE | `task/evaluation.py` → `evaluation/inngest_functions/check_evaluators.py` | Better location |
| CREATE | `evaluation/results.py` | EvaluatorsResult |
| RENAME | `infrastructure/step_outputs.py` → `infrastructure/results.py` | Consistency |

---

## Appendix: New Type Definitions

All new result models to add to `step_outputs.py`:

```python
# Workflow orchestration results
class WorkflowStartResult(BaseModel):
    run_id: UUID
    dependencies_created: int
    evaluators_created: int
    initial_ready_tasks: int

class WorkflowCompleteResult(BaseModel):
    run_id: UUID
    status: Literal["completed"] = "completed"
    final_score: float | None
    normalized_score: float | None
    evaluators_count: int = 0

class WorkflowFailedResult(BaseModel):
    run_id: UUID
    status: Literal["failed"] = "failed"
    error: str

# Task execution results  
class TaskExecuteResult(BaseModel):
    run_id: UUID
    task_id: UUID
    execution_id: UUID | None = None
    success: bool
    skipped: bool = False
    skip_reason: str | None = None
    outputs_count: int = 0
    questions_asked: int = 0
    error: str | None = None

class TaskPropagateResult(BaseModel):
    run_id: UUID
    task_id: UUID
    newly_ready_tasks: int
    workflow_complete: bool
    workflow_failed: bool

# Evaluation results
class EvaluatorsResult(BaseModel):
    task_id: UUID
    evaluators_found: int
    evaluators_run: int
    scores: list[float]

# Cleanup results
class RunCleanupResult(BaseModel):
    run_id: UUID
    status: str
    sandbox_terminated: bool
    sandbox_id: str | None = None

# Combined init result
class DagInitResult(BaseModel):
    dependency_count: int
    evaluator_count: int
```
