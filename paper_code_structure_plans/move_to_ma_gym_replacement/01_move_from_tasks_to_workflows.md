# 01: Task Schema & DAG Execution System

## Overview

This document details the plan to evolve h_arcane from single-task execution to a full DAG-based workflow system. The key insight is that **workflows are just tasks with subtasks** - a single benchmark task is simply a workflow with one node.

## Design Philosophy

1. **Unified Primitive**: `Task` is the only execution unit. A "workflow" is just a root task with children.
2. **User-Friendly API**: Researchers define tasks with a clean Python API; we handle the DAG mechanics.
3. **Event-Driven Orchestration**: Inngest handles all state transitions (already in h_arcane).
4. **Separation of Concerns**: Task definition (user) vs. execution orchestration (library).

---

## Part 1: File Structure Plan

### 1.1 Design Philosophy: Flat + `_internal`

**Goal:** Optimize for the researcher's import statement.

```python
# What users write - this is what matters
from h_arcane import Task, Resource, execute_task, BaseWorker

# NOT this
from h_arcane.core.task.schemas import Task  # ❌ Too deep
```

**Approach:** 
- Public API at top level (~3 files: task.py, runner.py, worker.py)
- Everything else in `_internal/` (users never import from here)
- Single `Task` type used everywhere (no DB vs SDK type split)
- Workers assigned directly to tasks, not passed to `execute_task()`

### 1.1.1 Naming Conventions

| Principle | Example | Rationale |
|-----------|---------|-----------|
| SDK types are clean nouns | `Resource`, `Task` | Users see the clean name |
| DB types use namespace separation | `h_arcane._internal.db.models.Resource` | Same name, different module - no conflict |
| Functions describe action | `execute_task()` not `run()` | Clear what it does |
| Results match function | `ExecutionResult` | Pairs with `execute_task()` |

**SDK vs Internal naming (namespace separation pattern):**
```python
# PUBLIC (h_arcane/task.py)
class Resource(BaseModel):
    """A file resource for task input."""
    path: str | Path
    name: str

# INTERNAL (h_arcane/_internal/db/models.py)  
class Resource(SQLModel, table=True):
    """A persisted resource record."""
    __tablename__ = "resources"
    # ...

# No conflict because users only do:
#   from h_arcane import Resource
# Never:
#   from h_arcane._internal.db.models import Resource
```

**Why NOT `_Resource` for internal types:**
- `_ClassName` pattern is uncommon in major packages (Pydantic, Django, SQLAlchemy)
- Looks like "temporary/helper" not "real concept"
- Namespace separation is cleaner and follows industry standards

### 1.2 Current Structure (for reference)

```
h_arcane/
├── __init__.py
├── core/                 # ← Will become _internal/
│   ├── agents/
│   ├── communication/
│   ├── db/
│   ├── evaluation/
│   └── infrastructure/
├── benchmarks/
└── api/
```

### 1.3 New Structure

```
h_arcane/
│
├── __init__.py           # THE public API - all exports here
├── task.py               # PUBLIC: Task, Resource, TaskStatus
├── runner.py             # PUBLIC: execute_task(), ExecutionResult
├── worker.py             # PUBLIC: BaseWorker protocol
│
├── _internal/            # Implementation details (users never import)
│   │
│   ├── db/               # Database layer
│   │   ├── __init__.py
│   │   ├── connection.py
│   │   ├── models.py     # SQLModel tables (TaskExecution, AgentConfig, etc.)
│   │   └── queries.py
│   │
│   ├── task/             # Task processing
│   │   ├── __init__.py
│   │   ├── registry.py   # TaskRegistry (DAG flattening, validation)
│   │   ├── propagation.py # on_task_completed, is_task_ready
│   │   ├── persistence.py # SDK Task → DB records
│   │   └── events.py     # TaskEvents constants
│   │
│   ├── agents/           # Agent/worker management
│   │   ├── __init__.py
│   │   ├── registry.py   # AgentRegistry (collects workers, persists to DB)
│   │   └── roles.py      # AgentRole enum
│   │
│   ├── inngest/          # Inngest orchestration
│   │   ├── __init__.py
│   │   ├── client.py     # Inngest client instance
│   │   ├── task_functions.py    # task-execute, task-propagate
│   │   ├── workflow_functions.py # workflow-start, workflow-complete
│   │   └── registry.py   # Function registration
│   │
│   ├── evaluation/       # Evaluation system (existing)
│   │   ├── __init__.py
│   │   ├── runner.py
│   │   ├── schemas.py
│   │   └── rules/
│   │       ├── base.py
│   │       ├── code_rule.py
│   │       └── llm_judge.py
│   │
│   ├── sandbox/          # E2B sandbox (existing)
│   │   ├── __init__.py
│   │   └── sandbox.py
│   │
│   └── communication/    # Agent messaging (existing)
│       ├── __init__.py
│       ├── schemas.py
│       └── service.py
│
├── benchmarks/           # Benchmark-specific (unchanged)
│   ├── gdpeval/
│   ├── minif2f/
│   └── researchrubrics/
│
└── api/                  # FastAPI server (unchanged)
    └── main.py
```

### 1.4 Public API Files (Detail)

#### `h_arcane/__init__.py`
```python
"""
H-ARCANE: Task and workflow execution for AI research.

Usage:
    from h_arcane import Task, execute_task, BaseWorker
    
    # Create a worker
    worker = ReactWorker(model="gpt-4o", tools=[...])
    
    # Define a task with worker assignment
    task = Task(
        name="Analyze Data",
        description="Process the quarterly report",
        assigned_to=worker,
        resources=[Resource(path="data/report.xlsx", name="Quarterly Report")],
    )
    
    # Run - worker is already on the task
    result = await execute_task(task)
    print(f"Success: {result.success}, Score: {result.score}")
"""

from h_arcane.task import Task, TaskStatus, Resource
from h_arcane.runner import execute_task, ExecutionResult
from h_arcane.worker import BaseWorker

__all__ = [
    # Task definition
    "Task",
    "TaskStatus",
    "Resource",
    # Worker protocol
    "BaseWorker",
    # Execution
    "execute_task",
    "ExecutionResult",
]
```

#### `h_arcane/task.py` (~200 lines)
```python
"""
User-facing Task model and related types.

This is the PUBLIC API for defining tasks.
"""

from __future__ import annotations
from pydantic import BaseModel, Field
from uuid import UUID, uuid4
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from h_arcane.worker import BaseWorker
    from h_arcane.benchmarks.types import AnyRubric


class TaskStatus(str, Enum):
    """Task execution status."""
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Resource(BaseModel):
    """
    User-provided resource definition.
    
    Users provide path and name, mime_type is derived from extension.
    """
    path: str | Path
    name: str
    
    @property
    def mime_type(self) -> str:
        """Derive MIME type from file extension."""
        import mimetypes
        mime, _ = mimetypes.guess_type(str(self.path))
        return mime or "application/octet-stream"


class Task(BaseModel):
    """
    A unit of work - can be atomic or a DAG of subtasks.
    
    Examples:
        # Single task with worker
        worker = ReactWorker(model="gpt-4o", tools=[...])
        task = Task(
            name="Write memo", 
            description="...",
            assigned_to=worker,
            resources=[Resource(path="data.xlsx", name="Data")],
        )
        
        # DAG workflow
        a = Task(name="Research", description="...", assigned_to=researcher)
        b = Task(name="Write", description="...", assigned_to=writer, depends_on=[a])
        workflow = Task(name="Report", assigned_to=writer, children=[a, b])
    """
    
    # Identity
    id: UUID = Field(default_factory=uuid4)
    name: str
    description: str
    
    # === Worker Assignment ===
    assigned_to: "BaseWorker" = Field(
        ...,  # Required
        description="Worker responsible for this task. Must be a BaseWorker instance."
    )
    full_team: list["BaseWorker"] | None = Field(
        default=None,
        description="Optional team for collaboration. If set, all workers can contribute actions."
    )
    
    # DAG structure
    children: list[Task] = Field(default_factory=list)
    depends_on: list[Task | UUID] = Field(default_factory=list)
    
    # I/O
    resources: list[Resource] = Field(default_factory=list)
    
    # Evaluation (optional) - rubric to evaluate task outputs
    evaluator: "AnyRubric | None" = None  # StagedRubric, MiniF2FRubric, etc.
    
    # --- Internal state (managed by system, not user) ---
    parent_id: UUID | None = Field(default=None, exclude=True)
    status: TaskStatus = Field(default=TaskStatus.PENDING, exclude=True)
    _output_resource_ids: list[UUID] = []
    
    model_config = {"arbitrary_types_allowed": True}  # Allow BaseWorker, AnyRubric
    
    @property
    def is_leaf(self) -> bool:
        return len(self.children) == 0
    
    @property
    def is_composite(self) -> bool:
        return len(self.children) > 0
    
    @property
    def dependency_ids(self) -> list[UUID]:
        """Resolve depends_on to UUIDs."""
        return [d.id if isinstance(d, Task) else d for d in self.depends_on]
    
    @property
    def effective_team(self) -> list["BaseWorker"]:
        """All workers that can work on this task."""
        if self.full_team:
            return self.full_team
        return [self.assigned_to]
```

#### `h_arcane/runner.py` (~120 lines)
```python
"""
User-facing execute_task() function and ExecutionResult.

This is the PUBLIC API for executing tasks.
"""

from __future__ import annotations
from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime
from typing import Any

from h_arcane.task import Task, TaskStatus


class TaskResult(BaseModel):
    """Result for a single task in a DAG."""
    task_id: UUID
    name: str
    status: TaskStatus
    score: float | None = None
    outputs: list[Any] = Field(default_factory=list)
    error: str | None = None


class ExecutionResult(BaseModel):
    """Result of running a task or workflow."""
    
    success: bool
    status: TaskStatus
    
    # Outputs from root task
    outputs: list[Any] = Field(default_factory=list)
    
    # Evaluation
    score: float | None = None
    evaluation_details: dict = Field(default_factory=dict)
    
    # Timing
    started_at: datetime
    completed_at: datetime | None = None
    duration_seconds: float = 0.0
    
    # Cost
    total_cost_usd: float = 0.0
    
    # Per-task results (for DAGs)
    task_results: dict[UUID, TaskResult] = Field(default_factory=dict)
    
    # Error info
    error: str | None = None


async def execute_task(
    task: Task,
    evaluator: "AnyRubric | None" = None,
    timeout_seconds: float | None = None,
    max_concurrent_tasks: int = 10,
    **config,
) -> ExecutionResult:
    """
    Execute a task (single or DAG workflow).
    
    Workers are attached directly to tasks via `assigned_to` and `full_team`.
    No worker argument needed - tasks carry their workers.
    
    Args:
        task: The task to execute (with assigned workers)
        evaluator: Optional evaluator (StagedRubric or callable)
        timeout_seconds: Maximum execution time
        max_concurrent_tasks: Concurrency limit for DAG execution
    
    Returns:
        ExecutionResult with success status, outputs, and scores
    
    Example:
        worker = ReactWorker(model="gpt-4o", tools=[...])
        task = Task(name="...", assigned_to=worker, ...)
        result = await execute_task(task)
    """
    # Import here to avoid circular imports
    from h_arcane._internal.task.registry import TaskRegistry
    from h_arcane._internal.agents.registry import AgentRegistry
    from h_arcane._internal.task.persistence import persist_experiment, persist_run
    from h_arcane._internal.db.connection import get_session
    from h_arcane._internal.inngest.client import inngest
    
    # 1. Validate and process task tree
    task_registry = TaskRegistry(task)
    
    # 2. Build agent registry (collects all workers from task tree)
    agent_registry = AgentRegistry()
    agent_registry.register_from_task(task)
    
    # 3. Persist to database
    async with get_session() as session:
        experiment = await persist_experiment(session, task, task_registry)
        run_record = await persist_run(session, experiment.id, config)
        
        # Persist all workers as AgentConfig records
        await agent_registry.persist(session, run_record.id)
        
        await session.commit()
    
    # 4. Trigger execution via Inngest
    await inngest.send("workflow/started", {
        "run_id": str(run_record.id),
        "experiment_id": str(experiment.id),
    })
    
    # 5. Wait for completion
    result = await _wait_for_completion(run_record.id, timeout_seconds)
    
    return result


async def _wait_for_completion(run_id: UUID, timeout: float | None) -> ExecutionResult:
    """Poll database until run completes or times out."""
    from h_arcane._internal.task.persistence import wait_for_run_completion
    return await wait_for_run_completion(run_id, timeout)
```

#### `h_arcane/worker.py` (~80 lines)
```python
"""
BaseWorker protocol for task execution.

This is the PUBLIC API for worker implementations.
Users implement this protocol to create custom workers.
"""

from __future__ import annotations
from typing import Protocol, Any, runtime_checkable
from uuid import UUID, uuid4
from abc import abstractmethod

from h_arcane.task import Task


@runtime_checkable
class BaseWorker(Protocol):
    """
    Protocol that all worker implementations must follow.
    
    Workers are self-contained with their tools, model config, and execution logic.
    Users pass worker instances to Task.assigned_to.
    
    Example implementation:
        class ReactWorker(BaseWorker):
            def __init__(self, model: str, tools: list, system_prompt: str = ""):
                self.id = uuid4()
                self.name = "react_worker"
                self.model = model
                self.tools = tools
                self.system_prompt = system_prompt
            
            async def execute(self, task: Task, context: ExecutionContext) -> ExecutionResult:
                # Implementation using OpenAI Agents SDK, etc.
                ...
    """
    
    # Required properties
    id: UUID
    name: str
    model: str
    tools: list[Any]
    system_prompt: str
    
    @abstractmethod
    async def execute(self, task: Task, context: "WorkerContext") -> "WorkerResult":
        """
        Execute the given task.
        
        Args:
            task: The task to execute
            context: Execution context (sandbox, resources, etc.)
        
        Returns:
            WorkerResult with outputs, actions, and status
        """
        ...


class WorkerContext:
    """Context provided to workers during execution."""
    
    run_id: UUID
    sandbox: Any  # E2B sandbox
    input_resources: list[Any]
    # ... other context


class WorkerResult:
    """
    Result returned by a worker's execute() method.
    
    NOTE: This is different from ExecutionResult (in runner.py) which is
    the user-facing result from execute_task(). WorkerResult is internal.
    """
    
    success: bool
    outputs: list[Any]
    actions: list[Any]  # Action trace for DB persistence
    error: str | None = None
```

### 1.5 Internal Files (Summary)

| File | Purpose |
|------|---------|
| **Database Layer** | |
| `_internal/db/models.py` | SQLModel tables: `TaskExecution`, `TaskStateEvent`, `TaskDependency`, `TaskEvaluator`, `AgentConfig`, modified `Experiment`, `Run`, `Resource` |
| `_internal/db/queries.py` | Query classes for all tables (see 1.5.1) |
| **Task Processing** | |
| `_internal/task/registry.py` | `TaskRegistry` - DAG flattening, validation, cycle detection |
| `_internal/task/propagation.py` | `on_task_completed()`, `is_task_ready()`, parent propagation |
| `_internal/task/persistence.py` | `persist_experiment()`, `persist_run()`, `persist_dependencies()`, `persist_task_evaluators()` |
| `_internal/task/events.py` | Event constants: `TASK_READY`, `TASK_COMPLETED`, etc. |
| `_internal/task/state.py` | `record_state_event()` - append to TaskStateEvent table |
| **Agent Management** | |
| `_internal/agents/registry.py` | `AgentRegistry` - collects workers from tasks, persists to DB |
| `_internal/agents/roles.py` | `AgentRole` enum: WORKER, STAKEHOLDER, MANAGER |
| **Inngest Functions** | |
| `_internal/inngest/task_functions.py` | Inngest functions: `execute_task`, `propagate_completion` |
| `_internal/inngest/eval_functions.py` | Inngest function: `check_and_run_evaluators` |
| `_internal/inngest/workflow_functions.py` | Inngest functions: `workflow_start`, `workflow_complete` |
| **Evaluation** | |
| `_internal/evaluation/serialization.py` | `deserialize_rubric()` - reconstruct rubric from stored config |

#### 1.5.1 Query Classes

```python
# _internal/db/queries.py

class TaskExecutionQueries:
    def create(self, run_id: UUID, task_id: UUID, agent_id: UUID) -> TaskExecution
    def get(self, execution_id: UUID) -> TaskExecution | None
    def get_by_task(self, run_id: UUID, task_id: UUID) -> list[TaskExecution]
    def get_latest_by_task(self, run_id: UUID, task_id: UUID) -> TaskExecution | None
    def update_status(self, execution_id: UUID, status: TaskStatus) -> None
    def get_running(self) -> list[TaskExecution]

class TaskStateEventQueries:
    def record(self, run_id: UUID, task_id: UUID, event_type: str, 
               old_status: str | None, new_status: str, **kwargs) -> TaskStateEvent
    def get_history(self, run_id: UUID, task_id: UUID) -> list[TaskStateEvent]
    def get_by_run(self, run_id: UUID) -> list[TaskStateEvent]

class TaskDependencyQueries:
    def create_for_run(self, run_id: UUID, task_tree: dict) -> list[TaskDependency]
    def get_blocking(self, run_id: UUID, task_id: UUID) -> list[TaskDependency]
    def get_waiting_on(self, run_id: UUID, task_id: UUID) -> list[TaskDependency]
    def mark_satisfied(self, run_id: UUID, dependency_task_id: UUID, 
                       execution_id: UUID) -> list[UUID]  # Returns newly unblocked task IDs

class ResourceQueries:
    def create_input(self, experiment_id: UUID, task_id: UUID, ...) -> Resource
    def create_output(self, task_execution_id: UUID, ...) -> Resource
    def get_inputs_for_task(self, experiment_id: UUID, task_id: UUID) -> list[Resource]
    def get_outputs_for_execution(self, execution_id: UUID) -> list[Resource]

class TaskEvaluatorQueries:
    def create(self, run_id: UUID, task_id: UUID, evaluator: AnyRubric) -> TaskEvaluator
    def get_by_task(self, run_id: UUID, task_id: UUID) -> list[TaskEvaluator]
    def get_pending(self) -> list[TaskEvaluator]
    def mark_running(self, evaluator_id: UUID) -> None
    def mark_completed(self, evaluator_id: UUID, score: float, evaluation_id: UUID) -> None
```

#### 1.5.2 Helper Functions (to be implemented)

The following helper functions are referenced in the plan and need implementation:

| Function | Location | Purpose |
|----------|----------|---------|
| `get_task(run_id, task_id)` | `_internal/task/queries.py` | Get task definition from task_tree JSON |
| `get_leaf_descendants(task)` | `_internal/task/registry.py` | Get all leaf tasks under a composite |
| `get_dependent_tasks(run_id, task_id)` | `_internal/db/queries.py` | Query TaskDependency table |
| `serialize_resource(resource)` | `_internal/task/persistence.py` | Serialize SDK Resource to JSON |
| `serialize_evaluator(evaluator)` | `_internal/task/persistence.py` | Serialize AnyRubric to JSON |
| `update_task_status(run_id, task_id, status)` | `_internal/task/state.py` | Update status + emit event |
| `complete_task(run_id, task_id, result)` | `_internal/task/state.py` | Mark complete + store outputs |
| `fail_task(run_id, task_id, error)` | `_internal/task/state.py` | Mark failed + store error |

**Note:** `AgentRegistry` is an in-memory transient object (not a Query class) that:
1. Collects workers from the task tree during `execute_task()`
2. Uses `AgentConfigQueries` internally to persist to DB
3. Provides worker → DB ID mapping for `Action.agent_id`

### 1.6 Import Graph

```
User imports:
    from h_arcane import Task, execute_task, BaseWorker
                │
                ▼
h_arcane/__init__.py
    ├── h_arcane/task.py      → Task, Resource, TaskStatus
    ├── h_arcane/runner.py    → execute_task, ExecutionResult
    └── h_arcane/worker.py    → BaseWorker

runner.py (internal imports):
    └── h_arcane/_internal/
        ├── task/registry.py      # TaskRegistry
        ├── task/persistence.py   # persist_experiment, persist_run
        ├── agents/registry.py    # AgentRegistry
        ├── db/connection.py
        └── inngest/client.py

_internal/inngest/task_functions.py:
    └── h_arcane/_internal/
        ├── task/propagation.py   # on_task_completed, is_task_ready
        ├── task/events.py        # TaskEvents
        ├── agents/registry.py    # Get worker DB IDs for Action.agent_id
        └── db/queries.py
```

### 1.7 Migration from Current Structure

```bash
# Step 1: Rename core/ to _internal/
mv h_arcane/core h_arcane/_internal

# Step 2: Create public API files
touch h_arcane/task.py
touch h_arcane/runner.py
touch h_arcane/worker.py   # BaseWorker protocol

# Step 3: Update all internal imports
# Change: from h_arcane.core.X import Y
# To:     from h_arcane._internal.X import Y

# Step 4: Update __init__.py to export from new files

# Step 5: Add new _internal modules
mkdir h_arcane/_internal/task
mkdir h_arcane/_internal/inngest
mkdir h_arcane/_internal/agents
```

### 1.8 Files to Create (Ordered)

```
Phase 1 - Public API:
  1. h_arcane/task.py           # Task, Resource, TaskStatus
  2. h_arcane/worker.py         # BaseWorker protocol
  3. h_arcane/runner.py         # execute_task(), ExecutionResult

Phase 2 - Rename existing:
  4. mv core/ → _internal/
  5. Update all imports in _internal/

Phase 3 - New internal modules (task/):
  6. _internal/task/__init__.py
  7. _internal/task/events.py
  8. _internal/task/registry.py
  9. _internal/task/propagation.py
  10. _internal/task/persistence.py

Phase 4 - New internal modules (agents/):
  11. _internal/agents/__init__.py
  12. _internal/agents/roles.py       # AgentRole enum
  13. _internal/agents/registry.py    # AgentRegistry

Phase 5 - Inngest reorganization:
  14. _internal/inngest/__init__.py
  15. _internal/inngest/client.py (move from infrastructure)
  16. _internal/inngest/task_functions.py
  17. _internal/inngest/eval_functions.py  # check_and_run_evaluators
  18. _internal/inngest/workflow_functions.py
  19. _internal/inngest/registry.py

Phase 6 - Database schema:
  20. _internal/db/models.py
      - TaskExecution (task attempts)
      - TaskStateEvent (event-sourced state changes)
      - TaskDependency (materialized dependency graph)
      - TaskEvaluator (evaluator bindings)
      - Resource (add task_id, task_execution_id, is_input)
      - AgentConfig (add role)
      - Experiment (add task_tree, root_task_id)
  21. _internal/db/queries.py
      - TaskExecutionQueries
      - TaskStateEventQueries
      - TaskDependencyQueries
      - TaskEvaluatorQueries
      - ResourceQueries (updated)

Phase 7 - Task state management:
  22. _internal/task/state.py  # record_state_event()
  23. _internal/task/persistence.py  # persist_experiment, persist_dependencies, persist_task_evaluators

Phase 8 - Evaluation support:
  24. _internal/evaluation/serialization.py  # deserialize_rubric()

Phase 9 - Final exports:
  25. h_arcane/__init__.py (update)
```

---

## Part 2: Task Schema Design

### 2.1 Resource Input Model (User-Facing)

Users need to provide actual files/content, not pre-existing database IDs:

```python
from pydantic import BaseModel, Field
from pathlib import Path
from uuid import UUID, uuid4
import mimetypes

class Resource(BaseModel):
    """
    A file resource for task input.
    
    Users provide path, name, content, or url.
    MIME type is derived from file extension if path provided.
    
    NOTE: This is the SDK type. The DB type with the same name lives in
    h_arcane._internal.db.models (namespace separation pattern).
    """
    path: str | Path | None = None
    name: str
    content: str | bytes | None = None
    url: str | None = None
    mime_type_override: str | None = Field(default=None, alias="mime_type")
    
    @property
    def mime_type(self) -> str:
        """Derive MIME type from file extension or use override."""
        if self.mime_type_override:
            return self.mime_type_override
        if self.path:
            mime, _ = mimetypes.guess_type(str(self.path))
            return mime or "application/octet-stream"
        return "text/plain"
```

### 2.2 Core Task Model (User-Facing)

```python
from typing import Any, TYPE_CHECKING
from enum import Enum

if TYPE_CHECKING:
    from h_arcane.worker import BaseWorker

class TaskStatus(str, Enum):
    """Task execution status."""
    PENDING = "pending"      # Not ready (dependencies not met)
    READY = "ready"          # Dependencies satisfied, waiting for execution
    RUNNING = "running"      # Currently executing
    COMPLETED = "completed"  # Successfully finished
    FAILED = "failed"        # Execution failed


class Task(BaseModel):
    """
    A unit of work in the execution system.
    
    Can be atomic (leaf node) or composite (has children).
    Supports both single-task benchmarks and complex DAG workflows.
    
    NOTE: This is the USER-FACING model. When persisted to DB, we convert
    to internal representations with UUIDs.
    """
    
    # Identity
    id: UUID = Field(default_factory=uuid4)
    name: str
    description: str
    
    # === Worker Assignment ===
    
    # Who is responsible for this task (REQUIRED for all tasks)
    # - For leaf tasks: the worker that executes the task
    # - For composite tasks: the "owner" who is accountable for completion
    #   (useful for tracking, notifications, and future manager-agent patterns)
    # Must be a BaseWorker instance - the actual worker object, not a string ID
    assigned_to: "BaseWorker"
    
    # Optional team of workers that can collaborate on this task
    # If provided, all workers in full_team can contribute actions
    # Credit assignment: each Action.agent_id tracks who did what
    full_team: list["BaseWorker"] | None = None
    
    # === DAG Structure ===
    
    # Children (subtasks) - defines the task hierarchy
    # If empty, this is an atomic/leaf task
    children: list["Task"] = Field(default_factory=list)
    
    # Dependencies - other tasks that must complete before this one starts
    # Accept Task objects directly (resolved to UUIDs internally)
    # Dependencies are within the same parent scope (sibling tasks)
    depends_on: list["Task" | UUID] = Field(default_factory=list)
    
    # Parent reference (set automatically by system, not by user)
    parent_id: UUID | None = None
    
    # === I/O (User-Facing) ===
    
    # Input resources - users provide Resource objects
    resources: list[Resource] = Field(default_factory=list)
    
    # Output resources populated on completion (internal use)
    _output_resource_ids: list[UUID] = Field(default_factory=list, exclude=True)
    
    # Resolved dependency IDs (set by TaskRegistry during processing)
    _resolved_dependency_ids: list[UUID] = Field(default_factory=list, exclude=True)
    
    # === Execution State (internal, managed by system) ===
    status: TaskStatus = Field(default=TaskStatus.PENDING)
    
    # === Evaluation (optional) ===
    # Rubric to evaluate task outputs on completion
    # Uses existing rubric types from h_arcane.benchmarks.types.AnyRubric
    evaluator: "AnyRubric | None" = None
    
    # === Computed Properties ===
    
    @property
    def is_leaf(self) -> bool:
        """Atomic task with no children."""
        return len(self.children) == 0
    
    @property
    def is_composite(self) -> bool:
        """Has children (is a sub-workflow)."""
        return len(self.children) > 0
    
    @property
    def dependency_ids(self) -> list[UUID]:
        """Resolve depends_on to UUIDs."""
        return [
            dep.id if isinstance(dep, Task) else dep
            for dep in self.depends_on
        ]
    
    @property
    def effective_team(self) -> list["BaseWorker"]:
        """Get all workers that can work on this task."""
        if self.full_team:
            return self.full_team
        return [self.assigned_to]
```

### 2.3 User-Facing Task Builder API

The researcher-facing API should be clean and intuitive:

```python
from h_arcane import Task, Resource, execute_task
from h_arcane.worker import BaseWorker

# ============================================
# STEP 0: Create workers (implements BaseWorker protocol)
# ============================================

# Workers are self-contained with their tools and configuration
analyst = ReactWorker(
    name="analyst",
    model="gpt-4o",
    tools=[read_file, write_file, analyze_data],
    system_prompt="You are a financial analyst...",
)

legal_expert = ReactWorker(
    name="legal_expert", 
    model="gpt-4o",
    tools=[read_file, search_legal_db],
    system_prompt="You are a legal compliance expert...",
)

writer = ReactWorker(
    name="writer",
    model="gpt-4o",
    tools=[read_file, write_file],
    system_prompt="You are a technical writer...",
)

reviewer = ReactWorker(
    name="reviewer",
    model="gpt-4o",
    tools=[read_file, approve_document],
    system_prompt="You are an executive reviewer...",
)

# ============================================
# EXAMPLE 1: Single-task benchmark (GDPEval style)
# ============================================

task = Task(
    name="Create Financial Memo",
    description="""
    Write a 2-page financial memo summarizing Q4 earnings.
    Include key metrics, trends, and recommendations.
    """,
    assigned_to=analyst,  # Worker object, not string!
    resources=[
        Resource(path="data/quarterly_earnings.xlsx", name="Q4 Earnings"),
        Resource(path="templates/memo_template.docx", name="Memo Template"),
    ],
)

# Run with just the task - worker is already attached
result = await execute_task(task)

# ============================================
# EXAMPLE 2: Multi-step workflow (DAG)
# ============================================

# Define tasks as variables so we can reference them in depends_on
gather_data = Task(
    name="Gather Financial Data",
    description="Collect and organize all financial records",
    assigned_to=analyst,
    resources=[Resource(path="data/raw_financials.csv", name="Raw Financials")],
)

legal_review = Task(
    name="Legal Review",
    description="Review all contracts and compliance",
    assigned_to=legal_expert,
    resources=[Resource(path="contracts/master_agreement.pdf", name="Master Agreement")],
)

draft_prospectus = Task(
    name="Draft Prospectus",
    description="Write the IPO prospectus document",
    assigned_to=writer,
    depends_on=[gather_data, legal_review],  # Task objects, not strings!
)

final_review = Task(
    name="Final Review",
    description="Executive sign-off on all materials",
    assigned_to=reviewer,
    depends_on=[draft_prospectus],
)

workflow = Task(
    name="IPO Preparation",
    description="Complete IPO readiness documentation",
    assigned_to=reviewer,  # Root task owner (for composite, often the final approver)
    children=[gather_data, legal_review, draft_prospectus, final_review],
)

# Run the workflow
result = await execute_task(workflow)

# ============================================
# EXAMPLE 3: Multi-worker collaboration on single task
# ============================================

# When multiple workers need to collaborate on one task
code_review = Task(
    name="Code Review",
    description="Review and approve the code changes",
    assigned_to=senior_dev,  # Primary owner - decides when task is done
    full_team=[senior_dev, junior_dev, security_reviewer],  # All can contribute
)

# Each worker's actions are tracked via Action.agent_id for credit assignment
# Task completes when assigned_to worker marks it complete

# ============================================
# EXAMPLE 4: Nested hierarchy (tree structure)
# ============================================

search_papers = Task(
    name="Search Papers", 
    description="...",
    assigned_to=researcher,
)
summarize = Task(
    name="Summarize Findings", 
    description="...", 
    assigned_to=researcher,
    depends_on=[search_papers],
)

lit_review = Task(
    name="Literature Review",
    description="Review existing research",
    assigned_to=researcher,  # Composite tasks also have an owner
    children=[search_papers, summarize],
)

data_collection = Task(
    name="Data Collection",
    description="Gather experimental data",
    assigned_to=lab_tech,
    depends_on=[lit_review],  # Depends on composite = wait for all its leaves
)

analysis = Task(
    name="Analysis",
    description="Analyze results",
    assigned_to=analyst,
    depends_on=[data_collection],
)

workflow = Task(
    name="Research Project",
    description="Complete research study",
    assigned_to=researcher,
    children=[lit_review, data_collection, analysis],
)
```

### 2.4 Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Dependencies by Task object | ✅ Required | Unambiguous, type-safe, no name collisions |
| `inputs` as Resource | ✅ User-friendly | Users provide paths/content, we handle DB persistence |
| Dependency scope | Siblings only | Keeps DAG simple; cross-level deps are implicit |
| Composite task completion | When all leaves complete | Matches fractal-os pattern |
| Status propagation | Bottom-up | Leaf completes → parent checks if all leaves done |
| `assigned_to` as `BaseWorker` | ✅ Object, not string | No resolution logic, type-safe, worker carries config |
| `full_team` for collaboration | ✅ Optional | Single-worker default, explicit multi-worker when needed |
| Workers on Task, not `execute_task()` | ✅ Task carries workers | Clear ownership, no ambiguous assignment |

#### Worker Assignment Philosophy

```
PRINCIPLE: Every task knows who does it.

┌─────────────────────────────────────────────────────────────┐
│ assigned_to: BaseWorker                                      │
│   - REQUIRED for all tasks                                   │
│   - Who is RESPONSIBLE for completion                        │
│   - Decides when task is "done"                              │
│                                                              │
│ full_team: list[BaseWorker] | None                          │
│   - OPTIONAL collaborators                                   │
│   - All team members can contribute Actions                  │
│   - Credit: Action.agent_id tracks who did what              │
│   - If None, only assigned_to works on task                  │
└─────────────────────────────────────────────────────────────┘

Why worker objects, not IDs?
  ✅ No string → worker resolution logic
  ✅ Type safety (can't pass wrong thing)
  ✅ Worker config is self-contained (tools, model, prompt)
  ✅ Clear at task definition time who executes

Why assigned_to is required?
  ✅ No ambiguity about ownership
  ✅ Clear completion semantics (owner decides "done")
  ✅ Explicit > implicit assignment
```

---

## Part 3: DAG Resolution & Validation

### 3.1 Task Tree Processing

When a user submits a task (single or DAG), we need to:

1. **Flatten the tree** into a task registry (id → Task)
2. **Resolve dependencies** (Task objects → UUIDs)
3. **Validate the DAG** (no cycles, all deps exist in tree)
4. **Set parent references** (link children to parents)
5. **Persist resources** (convert Resource → Resource records)
6. **Compute initial statuses** (which tasks are READY)

```python
class TaskRegistry:
    """
    Manages the flattened view of a task tree.
    Handles resolution, validation, and status computation.
    """
    
    def __init__(self, root_task: Task):
        self.root_id = root_task.id
        self.tasks: dict[UUID, Task] = {}
        
        self._flatten_tree(root_task, parent_id=None)
        self._resolve_dependencies()
        self._validate_dag()
        self._compute_initial_statuses()
    
    def _flatten_tree(self, task: Task, parent_id: UUID | None) -> None:
        """Recursively flatten task tree into registry."""
        task.parent_id = parent_id
        self.tasks[task.id] = task
        
        for child in task.children:
            self._flatten_tree(child, parent_id=task.id)
    
    def _resolve_dependencies(self) -> None:
        """Convert Task object deps to UUIDs, validate they exist."""
        for task in self.tasks.values():
            resolved_deps: list[UUID] = []
            for dep in task.depends_on:
                if isinstance(dep, Task):
                    dep_id = dep.id
                else:
                    dep_id = dep  # Already a UUID
                
                # Validate dependency exists in tree
                if dep_id not in self.tasks:
                    raise ValueError(
                        f"Task '{task.name}' depends on task ID {dep_id} "
                        f"which is not in the task tree"
                    )
                resolved_deps.append(dep_id)
            
            # Store resolved UUIDs
            task._resolved_dependency_ids = resolved_deps
    
    def _validate_dag(self) -> None:
        """Ensure no cycles in dependency graph using topological sort."""
        visited: set[UUID] = set()
        rec_stack: set[UUID] = set()
        
        def has_cycle(task_id: UUID) -> bool:
            visited.add(task_id)
            rec_stack.add(task_id)
            
            task = self.tasks[task_id]
            for dep_id in task._resolved_dependency_ids:
                if dep_id not in visited:
                    if has_cycle(dep_id):
                        return True
                elif dep_id in rec_stack:
                    return True
            
            rec_stack.remove(task_id)
            return False
        
        for task_id in self.tasks:
            if task_id not in visited:
                if has_cycle(task_id):
                    raise ValueError("Cycle detected in task dependency graph")
    
    def _compute_initial_statuses(self) -> None:
        """Mark tasks with no dependencies as READY."""
        for task in self.tasks.values():
            if task.is_leaf and not task._resolved_dependency_ids:
                task.status = TaskStatus.READY
    
    def get_leaf_tasks(self) -> list[Task]:
        """Get all leaf (atomic) tasks."""
        return [t for t in self.tasks.values() if t.is_leaf]
    
    def get_ready_tasks(self) -> list[Task]:
        """Get tasks that are ready to execute."""
        return [t for t in self.tasks.values() if t.status == TaskStatus.READY]
```

### 3.2 Dependency Resolution Rules

```
RULE 1: Direct dependency (Task object)
  task_b = Task(depends_on=[task_a])
  → task_b waits for task_a.status == COMPLETED

RULE 2: Composite dependency
  Task A depends_on CompositeTask C (which has children)
  → A waits for ALL leaves of C to be COMPLETED

RULE 3: Scope validation
  All tasks in depends_on must exist in the same task tree
  → Prevents dangling references

RULE 4: No string name-based dependencies
  depends_on=["TaskName"] is NOT supported
  → Use Task objects (preferred) or UUIDs (for deserialization)
  → Task objects provide type safety and refactoring support
```

---

## Part 4: SDK → PostgreSQL Data Flow

This section details how user-defined tasks flow into the database layer.

### 4.1 The `execute_task()` Entry Point

When a user calls `execute_task(task)`, we need to:

```python
async def execute_task(
    task: Task,
    evaluator: AnyRubric | None = None,
    timeout_seconds: float | None = None,
    max_concurrent_tasks: int = 10,
    **config,
) -> ExecutionResult:
    """
    Main entry point for executing a task (single or DAG).
    
    Workers are attached directly to tasks via `assigned_to` and `full_team`.
    No worker resolution needed here - tasks carry their workers.
    
    Flow:
    1. Validate and process task tree
    2. Build agent registry (collect all workers from tasks)
    3. Persist to database (Experiment, Run, Resources, AgentConfigs)
    4. Trigger execution via Inngest
    5. Wait for completion
    6. Return results
    """
    
    # Step 1: Build task registry (validates DAG)
    task_registry = TaskRegistry(task)
    
    # Step 2: Build agent registry (collects all workers from task tree)
    agent_registry = AgentRegistry()
    agent_registry.register_from_task(task)
    
    # Step 3: Persist to database
    async with db_session() as session:
        # Create Experiment (represents the task definition)
        experiment = await persist_experiment(session, task, task_registry)
        
        # Create Run (represents this execution attempt)
        run_record = await persist_run(session, experiment.id, config)
        
        # Persist all workers as AgentConfig records
        worker_db_ids = await agent_registry.persist(session, run_record.id)
        
        # Create Resource records for all inputs
        await persist_input_resources(session, run_record.id, task_registry)
        
        await session.commit()
    
    # Step 4: Trigger execution
    await inngest.send("workflow/started", {
        "run_id": str(run_record.id),
        "experiment_id": str(experiment.id),
    })
    
    # Step 5: Wait for completion (poll or webhook)
    result = await wait_for_completion(run_record.id, timeout=timeout_seconds)
    
    # Step 6: Return results
    return result
```

### 4.2 Agent Registry (Internal)

The `AgentRegistry` collects all workers referenced in the task tree, deduplicates them, and persists to DB:

```python
# h_arcane/_internal/agents/registry.py

from enum import Enum
from uuid import UUID
from sqlmodel import Session
from h_arcane.worker import BaseWorker


class AgentRole(str, Enum):
    """Role of an agent in a workflow."""
    WORKER = "worker"          # Executes tasks
    STAKEHOLDER = "stakeholder"  # Can be queried for info (future)
    MANAGER = "manager"        # Orchestrates work (future)


class AgentRegistry:
    """
    Internal registry that collects all workers from the task tree,
    deduplicates them, and persists to DB.
    
    Bridges SDK BaseWorker objects → DB AgentConfig records.
    """
    
    def __init__(self):
        self._workers: dict[UUID, BaseWorker] = {}  # worker.id -> worker
        self._roles: dict[UUID, AgentRole] = {}     # worker.id -> role
        self._db_ids: dict[UUID, UUID] = {}         # worker.id -> AgentConfig.id
    
    def register(self, worker: BaseWorker, role: AgentRole = AgentRole.WORKER) -> None:
        """
        Register a worker (idempotent - same worker won't duplicate).
        
        Uses worker.id for deduplication. Same worker object referenced
        in multiple tasks only creates one AgentConfig record.
        """
        if worker.id not in self._workers:
            self._workers[worker.id] = worker
            self._roles[worker.id] = role
    
    def register_from_task(self, task: Task) -> None:
        """
        Recursively register all workers from task tree.
        
        Collects:
        - assigned_to worker from each task
        - All workers in full_team (if present)
        - Recursively from children
        """
        # Register the assigned worker
        self.register(task.assigned_to, AgentRole.WORKER)
        
        # Register team members (if any)
        if task.full_team:
            for worker in task.full_team:
                self.register(worker, AgentRole.WORKER)
        
        # Recurse into children
        for child in task.children:
            self.register_from_task(child)
    
    async def persist(self, session: AsyncSession, run_id: UUID) -> dict[UUID, UUID]:
        """
        Persist all registered workers to AgentConfig table.
        
        Creates one AgentConfig record per unique worker.
        Uses AgentConfigQueries for consistency.
        
        Returns:
            Mapping of worker.id -> AgentConfig.id (DB primary key)
        """
        from h_arcane._internal.db.queries import AgentConfigQueries
        queries = AgentConfigQueries(session)
        
        for worker_id, worker in self._workers.items():
            config = await queries.create(
                run_id=run_id,
                name=worker.name,
                agent_type=worker.__class__.__name__,
                model=worker.model,
                system_prompt=worker.system_prompt or "",
                tools=[t.__name__ if callable(t) else str(t) for t in worker.tools],
                role=self._roles[worker_id],
            )
            self._db_ids[worker_id] = config.id
        
        return self._db_ids
    
    def get_db_id(self, worker: BaseWorker) -> UUID:
        """
        Get the DB AgentConfig.id for a worker.
        
        Call after persist() to map SDK worker objects to DB records.
        Used when recording Actions to set Action.agent_id.
        """
        if worker.id not in self._db_ids:
            raise ValueError(f"Worker '{worker.name}' not persisted. Call persist() first.")
        return self._db_ids[worker.id]
    
    @property
    def workers(self) -> list[BaseWorker]:
        """All registered workers."""
        return list(self._workers.values())
```

**Usage in task execution:**

```python
# When executing a task and recording actions
async def execute_task(task: Task, registry: AgentRegistry) -> None:
    worker = task.assigned_to
    
    # Get the DB ID for this worker (for Action.agent_id FK)
    agent_config_id = registry.get_db_id(worker)
    
    # Execute and record actions
    result = await worker.execute(task)
    
    for action in result.actions:
        action_record = Action(
            run_id=run_id,
            agent_id=agent_config_id,  # Links action to worker in DB
            action_type=action.type,
            input=action.input,
            output=action.output,
        )
        session.add(action_record)
```

### 4.4 Persisting the Task Tree

```python
async def persist_experiment(
    session: AsyncSession,
    root_task: Task,
    registry: TaskRegistry,
) -> Experiment:
    """
    Create Experiment record with task tree.
    
    The task tree is stored as JSON for simplicity.
    Individual task executions are tracked in TaskExecution table.
    """
    
    # Serialize task tree (without runtime state)
    task_tree = serialize_task_tree(root_task)
    
    experiment = Experiment(
        benchmark_name=BenchmarkName.CUSTOM,  # Or infer from task metadata
        task_id=str(root_task.id),
        task_description=root_task.description,
        ground_truth_rubric={},  # Populated if evaluator provided
        task_tree=task_tree,  # NEW FIELD: Full task DAG as JSON
    )
    
    session.add(experiment)
    return experiment


def serialize_task_tree(task: Task) -> dict:
    """
    Serialize task tree to JSON-compatible dict.
    
    Strips runtime state, keeps structure.
    """
    return {
        "id": str(task.id),
        "name": task.name,
        "description": task.description,
        "depends_on": [str(dep.id if isinstance(dep, Task) else dep) for dep in task.depends_on],
        "resources": [
            {"name": r.name, "path": str(r.path) if r.path else None} 
            for r in task.resources
        ],
        "children": [serialize_task_tree(child) for child in task.children],
        "evaluator": str(task.evaluator) if task.evaluator else None,
    }
```

### 4.5 Persisting Input Resources

```python
async def persist_input_resources(
    session: AsyncSession,
    run_id: UUID,
    registry: TaskRegistry,
) -> dict[UUID, list[UUID]]:
    """
    Create Resource records for all task inputs.
    
    Returns mapping: task_id -> [resource_ids]
    """
    task_to_resources: dict[UUID, list[UUID]] = {}
    
    for task in registry.tasks.values():
        resource_ids = []
        
        for inp in task.resources:
            # Create Resource record
            resource = await create_stored_resource(session, run_id, inp)
            resource_ids.append(resource.id)
        
        task_to_resources[task.id] = resource_ids
    
    return task_to_resources


async def create_stored_resource(
    session: AsyncSession,
    run_id: UUID,
    sdk_resource: Resource,  # SDK type
) -> "StoredResource":  # DB type (same name, different module)
    """
    Convert SDK Resource to DB StoredResource record.
    
    Handles:
    - File paths: Read file, store content/path
    - Inline content: Store directly
    - URLs: Fetch and store
    """
    from h_arcane._internal.db.models import Resource as StoredResource
    
    if sdk_resource.path:
        path = Path(sdk_resource.path)
        if not path.exists():
            raise FileNotFoundError(f"Input file not found: {sdk_resource.path}")
        
        stored = StoredResource(
            run_id=run_id,
            name=sdk_resource.name,
            mime_type=sdk_resource.mime_type,
            file_path=str(path.absolute()),
            size_bytes=path.stat().st_size,
            is_input=True,
        )
    
    elif sdk_resource.content:
        # Inline content handling logic...
        stored = StoredResource(
            run_id=run_id,
            name=sdk_resource.name,
            mime_type=sdk_resource.mime_type,
            file_path="...", # Path to stored blob
            size_bytes=len(sdk_resource.content),
            is_input=True,
        )
    
    elif sdk_resource.url:
        # URL fetching logic...
        stored = StoredResource(
            run_id=run_id,
            name=sdk_resource.name,
            mime_type=sdk_resource.mime_type,
            file_path="...", # Path to downloaded content
            size_bytes=0, # Updated after download
            is_input=True,
        )
    
    else:
        raise ValueError("Resource must have path, content, or url")
    
    session.add(stored)
    return stored
```

### 4.6 Database Schema Summary

```
┌─────────────────────────────────────────────────────────────────┐
│                         Experiment                               │
│  - id (PK)                                                       │
│  - task_tree: JSON    ← Full DAG structure                       │
│  - task_description   ← Root task description                    │
│  - ground_truth_rubric: JSON                                     │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ 1:N
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                            Run                                   │
│  - id (PK)                                                       │
│  - experiment_id (FK)                                            │
│  - status: RunStatus                                             │
│  - task_states: JSON  ← Runtime state of each task               │
│  - agent_config: JSON                                            │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ 1:N
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                       TaskExecution                              │
│  - id (PK)                                                       │
│  - run_id (FK)                                                   │
│  - task_id: UUID      ← References task in task_tree             │
│  - status: TaskStatus                                            │
│  - started_at, completed_at                                      │
│  - output_resource_ids: JSON                                     │
│  - score, evaluation_details: JSON                               │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ N:N
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                         Resource                                 │
│  - id (PK)                                                       │
│  - run_id (FK)        ← Which run this belongs to                │
│  - name, mime_type, file_path, size_bytes                        │
└─────────────────────────────────────────────────────────────────┘
```

---

## Part 5: Execution Orchestration

### 5.1 Event-Driven Architecture (via Inngest)

Leverage existing Inngest infrastructure with new events:

```python
# === New Events ===

class TaskEvents:
    """Task lifecycle events."""
    
    TASK_READY = "task/ready"           # Dependencies satisfied
    TASK_STARTED = "task/started"       # Execution began
    TASK_COMPLETED = "task/completed"   # Execution succeeded
    TASK_FAILED = "task/failed"         # Execution failed

class WorkflowEvents:
    """Workflow-level events."""
    
    WORKFLOW_STARTED = "workflow/started"      # Root task execution began
    WORKFLOW_COMPLETED = "workflow/completed"  # All tasks done
    WORKFLOW_FAILED = "workflow/failed"        # Unrecoverable failure
```

### 5.2 Task Propagation Logic

Inspired by fractal-os `propagate_task_completion`:

```python
async def on_task_completed(task_id: UUID, run_id: UUID) -> None:
    """
    Called when a task completes. Propagates status changes.
    
    1. Update parent task status (check if all children done)
    2. Check dependent tasks (are they now ready?)
    3. Trigger ready tasks
    """
    task = get_task(run_id, task_id)
    
    # Step 1: Propagate up to parent
    if task.parent_id:
        await propagate_to_parent(run_id, task.parent_id)
    
    # Step 2: Check consumers (tasks that depend on this one)
    consumers = get_dependent_tasks(run_id, task_id)
    
    for consumer in consumers:
        if is_task_ready(run_id, consumer.id):
            # All dependencies satisfied
            consumer.status = TaskStatus.READY
            await inngest.send(TaskEvents.TASK_READY, {
                "run_id": run_id,
                "task_id": consumer.id,
            })


async def propagate_to_parent(run_id: UUID, parent_id: UUID) -> None:
    """
    Check if parent task should be marked complete.
    A composite task is COMPLETED when all its leaf descendants are COMPLETED.
    """
    parent = get_task(run_id, parent_id)
    
    if parent.is_leaf:
        return  # Leaf tasks don't have children to check
    
    leaves = get_leaf_descendants(parent)
    
    if all(leaf.status == TaskStatus.COMPLETED for leaf in leaves):
        parent.status = TaskStatus.COMPLETED
        await inngest.send(TaskEvents.TASK_COMPLETED, {
            "run_id": run_id,
            "task_id": parent_id,
        })
        
        # Continue propagation up
        if parent.parent_id:
            await propagate_to_parent(run_id, parent.parent_id)


def is_task_ready(run_id: UUID, task_id: UUID) -> bool:
    """
    Check if a task's dependencies are satisfied.
    
    A task is ready when:
    1. All tasks in depends_on are COMPLETED
    2. All input resources exist (if any)
    """
    task = get_task(run_id, task_id)
    
    # Check explicit dependencies
    for dep_id in task.depends_on:
        dep_task = get_task(run_id, dep_id)
        
        # If dependency is composite, check all its leaves
        if dep_task.is_composite:
            leaves = get_leaf_descendants(dep_task)
            if not all(leaf.status == TaskStatus.COMPLETED for leaf in leaves):
                return False
        else:
            if dep_task.status != TaskStatus.COMPLETED:
                return False
    
    # Check that input resources are available
    # For file-based resources, we check if they exist on disk.
    for resource in task.resources:
        if resource.path and not Path(resource.path).exists():
            return False
    
    return True
```

### 5.3 Inngest Function Definitions

```python
# === Inngest Functions ===

@inngest.create_function(
    fn_id="task-execute",
    trigger=inngest.TriggerEvent(event=TaskEvents.TASK_READY),
    concurrency=[inngest.Concurrency(limit=15)],
)
async def execute_task(ctx: inngest.Context) -> None:
    """Execute a ready task."""
    run_id = ctx.event.data["run_id"]
    task_id = ctx.event.data["task_id"]
    
    task = await ctx.step.run("get-task", lambda: get_task(run_id, task_id))
    
    # Only execute leaf tasks
    if not task.is_leaf:
        return  # Composite tasks don't execute directly
    
    # Mark as running
    await ctx.step.run("mark-running", lambda: update_task_status(
        run_id, task_id, TaskStatus.RUNNING
    ))
    
    # Execute with agent
    try:
        result = await ctx.step.run("execute", lambda: run_agent_on_task(
            run_id, task_id
        ))
        
        # Mark complete and propagate
        await ctx.step.run("complete", lambda: complete_task(
            run_id, task_id, result
        ))
        
    except Exception as e:
        await ctx.step.run("fail", lambda: fail_task(run_id, task_id, str(e)))


@inngest.create_function(
    fn_id="task-propagate",
    trigger=inngest.TriggerEvent(event=TaskEvents.TASK_COMPLETED),
)
async def propagate_completion(ctx: inngest.Context) -> None:
    """Handle task completion propagation."""
    run_id = ctx.event.data["run_id"]
    task_id = ctx.event.data["task_id"]
    
    await ctx.step.run("propagate", lambda: on_task_completed(task_id, run_id))
```

### 5.4 Evaluation Execution Flow

Evaluations are bound to tasks and triggered automatically on task completion.

#### 5.4.1 Evaluation Storage in DB

When a task is persisted, its evaluator is stored in the `TaskExecution` or as a reference:

```python
# === NEW: TaskEvaluator table (binds evaluators to tasks) ===
class TaskEvaluator(SQLModel, table=True):
    """
    Binds an evaluator (rubric) to a task.
    
    When a task completes, we query this table to find evaluators to run.
    Supports multiple evaluators per task (e.g., different rubric types).
    """
    __tablename__ = "task_evaluators"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    run_id: UUID = Field(foreign_key="runs.id", index=True)
    task_id: UUID = Field(index=True)  # References task in the DAG
    
    # Evaluator definition (serialized rubric)
    evaluator_type: str  # "staged_rubric", "minif2f_rubric", etc.
    evaluator_config: dict = Field(sa_column=Column(JSON))  # Serialized rubric
    
    # Status
    status: str = Field(default="pending")  # pending, running, completed, failed
    
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    __table_args__ = (
        Index("ix_task_evaluators_run_task", "run_id", "task_id"),
    )
```

#### 5.4.2 Persisting Task Evaluators

When tasks are persisted, their evaluators are stored:

```python
async def persist_task_evaluators(
    session: AsyncSession,
    run_id: UUID,
    registry: TaskRegistry,
) -> None:
    """
    Create TaskEvaluator records for all tasks with evaluators.
    
    Called during execute_task() after task tree is persisted.
    """
    for task in registry.tasks.values():
        if task.evaluator is not None:
            evaluator_record = TaskEvaluator(
                run_id=run_id,
                task_id=task.id,
                evaluator_type=type(task.evaluator).__name__,
                evaluator_config=task.evaluator.model_dump(mode="json"),
            )
            session.add(evaluator_record)
```

#### 5.4.3 Event Flow for Evaluation

```
┌─────────────────┐     ┌─────────────────────┐     ┌────────────────────┐
│  Task Executes  │────▶│  task/completed     │────▶│  propagate_        │
│  (worker runs)  │     │  event emitted      │     │  completion        │
└─────────────────┘     └─────────────────────┘     └────────────────────┘
                                                              │
                                                              │ Also triggers:
                                                              ▼
                        ┌─────────────────────┐     ┌────────────────────┐
                        │  check_and_run_     │◀────│  task/completed    │
                        │  evaluators         │     │  (same event)      │
                        └─────────────────────┘     └────────────────────┘
                                  │
                                  │ Query TaskEvaluator table
                                  ▼
                        ┌─────────────────────┐
                        │  For each evaluator:│
                        │  invoke evaluate_   │
                        │  task_run           │
                        └─────────────────────┘
                                  │
                                  ▼
                        ┌─────────────────────┐
                        │  Store results in   │
                        │  CriterionResult,   │
                        │  Evaluation tables  │
                        └─────────────────────┘
```

#### 5.4.4 Inngest Function for Evaluation Triggering

```python
@inngest.create_function(
    fn_id="task-check-evaluators",
    trigger=inngest.TriggerEvent(event=TaskEvents.TASK_COMPLETED),
    retries=1,
)
async def check_and_run_evaluators(ctx: inngest.Context) -> dict:
    """
    Check if completed task has evaluators and run them.
    
    Subscribes to same task/completed event as propagate_completion.
    Multiple Inngest functions can subscribe to the same event.
    """
    run_id = UUID(ctx.event.data["run_id"])
    task_id = UUID(ctx.event.data["task_id"])
    
    # Query for evaluators bound to this task
    async def get_evaluators():
        evaluators = queries.task_evaluators.get_by_task(run_id, task_id)
        return [e.model_dump(mode="json") for e in evaluators]
    
    evaluator_dicts = await ctx.step.run("get-evaluators", get_evaluators)
    
    if not evaluator_dicts:
        return {"task_id": str(task_id), "evaluators_found": 0}
    
    # Load task execution data for evaluation
    async def load_task_data():
        execution = queries.task_executions.get_by_task(run_id, task_id)
        outputs = queries.resources.get_by_task_execution(execution.id)
        task_def = queries.get_task_definition(run_id, task_id)
        return {
            "task_input": task_def["description"],
            "output_resource_ids": [str(r.id) for r in outputs],
            "agent_reasoning": execution.output_text or "",
        }
    
    task_data = await ctx.step.run("load-task-data", load_task_data)
    
    # Run each evaluator
    results = []
    for eval_dict in evaluator_dicts:
        evaluator = TaskEvaluator(**eval_dict)
        
        # Mark evaluator as running
        async def mark_running(e=evaluator):
            e.status = "running"
            queries.task_evaluators.update(e)
            return None
        
        await ctx.step.run(f"mark-running-{evaluator.id}", mark_running)
        
        # Deserialize and invoke the appropriate rubric type
        rubric = deserialize_rubric(evaluator.evaluator_type, evaluator.evaluator_config)
        
        # Invoke the existing evaluate_task_run function
        result = await ctx.step.invoke(
            step_id=f"evaluate-{evaluator.id}",
            function=evaluate_task_run,
            data=TaskEvaluationEvent(
                run_id=str(run_id),
                task_input=task_data["task_input"],
                agent_reasoning=task_data["agent_reasoning"],
                agent_outputs=task_data["output_resource_ids"],
                rubric=rubric,
            ).model_dump(mode="json"),
        )
        
        # Mark evaluator as completed
        async def mark_completed(e=evaluator, r=result):
            e.status = "completed"
            queries.task_evaluators.update(e)
            return None
        
        await ctx.step.run(f"mark-completed-{evaluator.id}", mark_completed)
        
        results.append({
            "evaluator_id": str(evaluator.id),
            "score": result.normalized_score,
        })
    
    return {
        "task_id": str(task_id),
        "evaluators_found": len(evaluator_dicts),
        "results": results,
    }


def deserialize_rubric(evaluator_type: str, config: dict) -> AnyRubric:
    """Deserialize rubric from stored config."""
    from h_arcane.benchmarks.gdpeval.rubric import StagedRubric
    from h_arcane.benchmarks.minif2f.rubric import MiniF2FRubric
    from h_arcane.benchmarks.researchrubrics.rubric import ResearchRubricsRubric
    
    type_map = {
        "StagedRubric": StagedRubric,
        "MiniF2FRubric": MiniF2FRubric,
        "ResearchRubricsRubric": ResearchRubricsRubric,
    }
    
    rubric_class = type_map.get(evaluator_type)
    if not rubric_class:
        raise ValueError(f"Unknown evaluator type: {evaluator_type}")
    
    return rubric_class.model_validate(config)
```

#### 5.4.5 Key Design Decisions for Evaluation

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Separate `TaskEvaluator` table | ✅ | Decouples eval binding from task definition, enables multiple evals per task |
| Same event triggers eval + propagation | ✅ | Inngest handles fan-out, no need for separate event |
| Reuse existing `evaluate_task_run` | ✅ | Leverage existing rubric evaluation infrastructure |
| Store evaluator as serialized JSON | ✅ | Flexible, supports any rubric type |

---

## Part 6: Researcher API (Top-Level Interface)

### 6.1 The `execute_task()` Function

The primary entry point for researchers. Workers are attached directly to tasks:

```python
from h_arcane import execute_task, Task, Resource

# ============================================
# Simplest usage - single task with assigned worker
# ============================================

analyst = ReactWorker(model="gpt-4o", tools=[...])

task = Task(
    name="Write Memo",
    description="Create a financial summary",
    assigned_to=analyst,  # Worker attached to task
    resources=[Resource(path="data/earnings.xlsx", name="Earnings Data")],
)

# Run just takes the task - worker is already assigned
result = await execute_task(task)

# ============================================
# DAG workflow - each task has its worker
# ============================================

research = Task(
    name="Research",
    assigned_to=researcher,
    resources=[...],
)

writing = Task(
    name="Write Report",
    assigned_to=writer,
    depends_on=[research],
)

workflow = Task(
    name="Report Generation",
    assigned_to=writer,  # Root task owner
    children=[research, writing],
)

result = await execute_task(
    task=workflow,
    evaluator=my_rubric,
    max_concurrent_tasks=5,
    timeout_seconds=3600,
)

# Access results
print(f"Success: {result.success}")
print(f"Score: {result.score}")
print(f"Outputs: {result.outputs}")
for task_id, task_result in result.task_results.items():
    print(f"  {task_result.name}: {task_result.status}")
```

### 6.2 Worker Assignment Patterns

Workers are assigned at task definition time, not at `execute_task()` time:

```python
# ============================================
# Pattern 1: One worker per task (most common)
# ============================================

task = Task(
    name="Analyze data",
    assigned_to=analyst,  # This worker does this task
)

# ============================================
# Pattern 2: Team collaboration on single task
# ============================================

code_review = Task(
    name="Code Review",
    assigned_to=senior_dev,  # Owner - decides when done
    full_team=[senior_dev, junior_dev, security_expert],  # All can contribute
)
# Each worker's actions tracked via Action.agent_id
# Credit assignment: query actions by agent_id

# ============================================
# Pattern 3: Same worker, multiple tasks
# ============================================

# Reuse worker object across tasks
analyst = ReactWorker(model="gpt-4o", tools=[...])

task_1 = Task(name="Task 1", assigned_to=analyst)
task_2 = Task(name="Task 2", assigned_to=analyst)
task_3 = Task(name="Task 3", assigned_to=analyst)

# Same worker instance - creates ONE AgentConfig record in DB
# (AgentRegistry deduplicates by worker.id)

# ============================================
# Pattern 4: Specialized workers per task type
# ============================================

# Define specialized workers
researcher = ReactWorker(
    model="gpt-4o",
    tools=[web_search, arxiv_search, semantic_scholar],
    system_prompt="You are a research assistant...",
)

analyst = ReactWorker(
    model="gpt-4o", 
    tools=[pandas_tool, matplotlib_tool, statistics_tool],
    system_prompt="You are a data analyst...",
)

writer = ReactWorker(
    model="gpt-4o",
    tools=[write_file, format_document],
    system_prompt="You are a technical writer...",
)

# Assign based on task needs
research_task = Task(name="Literature Review", assigned_to=researcher)
analysis_task = Task(name="Data Analysis", assigned_to=analyst, depends_on=[research_task])
report_task = Task(name="Write Report", assigned_to=writer, depends_on=[analysis_task])
```

### 6.3 Why Workers on Tasks (Not `execute_task()`)?

| Approach | Pros | Cons |
|----------|------|------|
| ❌ `execute_task(task, agent)` | Simple signature | Ambiguous for DAGs - which task gets which agent? |
| ❌ `execute_task(task, agents={...})` | Explicit mapping | String keys are fragile, verbose |
| ✅ `task.assigned_to=worker` | Clear ownership, type-safe | Slightly more verbose task definitions |

**Decision: Workers on tasks because:**

1. **No ambiguity**: Each task knows exactly who executes it
2. **Type safety**: Can't accidentally pass wrong type
3. **Self-documenting**: Task definition shows the full execution plan
4. **Flexible**: Easy to assign same or different workers per task
5. **Credit assignment**: Built-in via `Action.agent_id`

### 6.4 Result Object

```python
class ExecutionResult(BaseModel):
    """Result of running a task/workflow."""
    
    # Overall status
    success: bool
    status: TaskStatus
    
    # Outputs from root task (or aggregated from leaves)
    outputs: list[Resource]
    
    # Evaluation results (if evaluator provided)
    score: float | None = None
    evaluation_details: dict = {}
    
    # Timing
    started_at: datetime
    completed_at: datetime
    duration_seconds: float
    
    # Cost tracking
    total_cost_usd: float = 0.0
    
    # Per-task results (for DAGs)
    task_results: dict[UUID, TaskResult] = {}
    
    # Full execution trace (for debugging/training)
    trace: ExecutionTrace | None = None
    
    # Error info (if failed)
    error: str | None = None
```

---

## Part 7: Database Schema Updates

### 7.1 Entity Relationship Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Experiment                                   │
│  - id                                                                │
│  - task_tree: JSON (DAG template with task definitions)              │
│  - root_task_id: UUID                                                │
└─────────────────────────────────────────────────────────────────────┘
         │
         │ 1:N
         ▼
┌─────────────────────────────────────────────────────────────────────┐
│                            Run                                       │
│  - id                                                                │
│  - experiment_id FK                                                  │
│  - overall status, timing, cost                                      │
└─────────────────────────────────────────────────────────────────────┘
         │
         │ 1:N (materialized at run start)
         ├──────────────────────────────────────────┐
         ▼                                          ▼
┌────────────────────┐                    ┌────────────────────┐
│  TaskDependency    │                    │  TaskExecution     │
│  - run_id FK       │                    │  - run_id FK       │
│  - dependent_id    │                    │  - task_id         │
│  - dependency_id   │                    │  - attempt_number  │
│  - is_satisfied    │                    │  - agent_id FK     │
└────────────────────┘                    │  - status          │
                                          └────────────────────┘
                                                   │
                                                   │ 1:N (outputs)
                                                   ▼
                                          ┌────────────────────┐
                                          │     Resource       │
                                          │  (is_input=False)  │
                                          │  - execution_id FK │
                                          └────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│  Resource (is_input=True) - Input resources belong to Experiment    │
│  - experiment_id FK                                                  │
│  - task_id (which task in the template)                              │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│  TaskStateEvent - Append-only event log                              │
│  - run_id FK                                                         │
│  - task_id                                                           │
│  - task_execution_id FK (nullable)                                   │
│  - event_type, old_status, new_status, timestamp                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 7.2 Core Tables

```python
# ═══════════════════════════════════════════════════════════════════
# Experiment (template/definition - existing, modified)
# ═══════════════════════════════════════════════════════════════════

class Experiment(SQLModel, table=True):
    """
    A workflow/task definition template.
    
    Contains the full DAG structure as JSON. This is the "blueprint"
    that gets instantiated when a Run is created.
    """
    __tablename__ = "experiments"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    
    # Benchmark identification
    benchmark_name: BenchmarkName = Field(index=True)
    task_id: str = Field(index=True)  # Unique per benchmark_name
    
    # Task definition
    task_description: str
    
    # NEW: Full task DAG as JSON
    task_tree: dict = Field(
        sa_column=Column(JSON),
        description="Full DAG structure with task definitions, dependencies, evaluators"
    )
    
    # NEW: Root task ID for easy access
    root_task_id: UUID | None = None
    
    # Ground truth evaluation data
    ground_truth_rubric: dict = Field(sa_column=Column(JSON))
    
    # Metadata
    benchmark_specific_data: dict = Field(default_factory=dict, sa_column=Column(JSON))
    category: str = Field(index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ═══════════════════════════════════════════════════════════════════
# Run (one execution of an experiment - existing, simplified)
# ═══════════════════════════════════════════════════════════════════

class Run(SQLModel, table=True):
    """
    One execution attempt of an Experiment.
    
    State tracking moved to TaskExecution and TaskStateEvent tables.
    """
    __tablename__ = "runs"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    experiment_id: UUID = Field(foreign_key="experiments.id", index=True)
    
    # Overall status (derived from task states)
    status: RunStatus = Field(default=RunStatus.PENDING)
    error_message: str | None = None
    
    # E2B sandbox tracking
    e2b_sandbox_id: str | None = None
    
    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    
    # Results (aggregated from task evaluations)
    final_score: float | None = None
    normalized_score: float | None = None
    
    # Cost tracking
    total_cost_usd: float | None = None
```

### 7.3 Task Execution Tables

```python
# ═══════════════════════════════════════════════════════════════════
# TaskExecution - One worker's attempt to execute a task
# ═══════════════════════════════════════════════════════════════════

class TaskExecution(SQLModel, table=True):
    """
    One worker's attempt to execute a task.
    
    Multiple executions per (run, task) are allowed:
    - Retries after failure
    - Different workers trying same task
    - Manager-agent spawning multiple attempts
    """
    __tablename__ = "task_executions"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    run_id: UUID = Field(foreign_key="runs.id", index=True)
    task_id: UUID = Field(index=True)  # References task in task_tree JSON
    
    # Which attempt is this?
    attempt_number: int = Field(default=1)
    
    # Worker assignment
    agent_id: UUID | None = Field(foreign_key="agent_configs.id", index=True)
    
    # Lifecycle
    status: TaskStatus = Field(default=TaskStatus.PENDING, index=True)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    
    # Results
    output_text: str | None = None  # Quick text summary
    error: dict | None = Field(default=None, sa_column=Column(JSON))
    
    # Evaluation (populated after completion)
    score: float | None = None
    evaluation_details: dict = Field(default_factory=dict, sa_column=Column(JSON))
    
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    __table_args__ = (
        Index("ix_task_executions_run_task", "run_id", "task_id"),
        Index("ix_task_executions_status", "status"),
    )


# ═══════════════════════════════════════════════════════════════════
# TaskStateEvent - Event-sourced state changes (append-only)
# ═══════════════════════════════════════════════════════════════════

class TaskStateEvent(SQLModel, table=True):
    """
    Event log for task state transitions.
    
    Each row = one state change. Immutable append-only.
    Enables: replay, audit trail, analytics, "what happened to task X?"
    
    This is the source of truth for task state history.
    TaskExecution.status is the current state (derived/denormalized).
    """
    __tablename__ = "task_state_events"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    run_id: UUID = Field(foreign_key="runs.id", index=True)
    task_id: UUID = Field(index=True)  # References task in task_tree JSON
    
    # Which execution (if any) caused this event
    task_execution_id: UUID | None = Field(
        foreign_key="task_executions.id", 
        index=True, 
        default=None
    )
    
    # State transition
    event_type: str = Field(index=True)  # "status_change", "assigned", "retry", "error"
    old_status: str | None = None
    new_status: str
    
    # Context
    triggered_by: str | None = None  # "dependency_satisfied", "worker_started", "timeout"
    metadata: dict = Field(default_factory=dict, sa_column=Column(JSON))
    
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    __table_args__ = (
        Index("ix_task_state_events_run_task", "run_id", "task_id"),
        Index("ix_task_state_events_timestamp", "timestamp"),
        Index("ix_task_state_events_type", "event_type"),
    )


# ═══════════════════════════════════════════════════════════════════
# TaskDependency - Materialized dependency edges
# ═══════════════════════════════════════════════════════════════════

class TaskDependency(SQLModel, table=True):
    """
    Materialized dependency edges for queryability.
    
    Created when a Run starts (copied from task_tree JSON).
    Updated as tasks complete (is_satisfied = True).
    
    Enables fast queries:
    - "What's blocking task X?"
    - "What tasks will unblock when X completes?"
    """
    __tablename__ = "task_dependencies"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    run_id: UUID = Field(foreign_key="runs.id", index=True)
    
    # The task that waits
    dependent_task_id: UUID = Field(index=True)
    
    # The task it waits for
    dependency_task_id: UUID = Field(index=True)
    
    # Satisfaction tracking
    is_satisfied: bool = Field(default=False, index=True)
    satisfied_at: datetime | None = None
    satisfied_by_execution_id: UUID | None = Field(
        foreign_key="task_executions.id",
        default=None
    )
    
    __table_args__ = (
        Index("ix_task_deps_waiting", "run_id", "dependent_task_id"),
        Index("ix_task_deps_blocking", "run_id", "dependency_task_id"),
        Index("ix_task_deps_unsatisfied", "run_id", "is_satisfied"),
    )
```

### 7.4 Resource Table (Updated)

```python
# ═══════════════════════════════════════════════════════════════════
# Resource - Files bound to tasks (not just runs)
# ═══════════════════════════════════════════════════════════════════

class Resource(SQLModel, table=True):
    """
    A file resource.
    
    Two ownership patterns:
    - INPUT:  Belongs to task definition (experiment_id + task_id)
    - OUTPUT: Belongs to task execution (task_execution_id)
    
    This enables tracking resource flow through the DAG:
    - "What inputs did task X have?"
    - "What outputs did task Y produce?"
    """
    __tablename__ = "resources"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    
    # === INPUT RESOURCES (defined in task template) ===
    # These belong to the Experiment/task definition
    experiment_id: UUID | None = Field(
        foreign_key="experiments.id", 
        index=True, 
        default=None
    )
    task_id: UUID | None = Field(
        index=True, 
        default=None,
        description="Which task in the DAG this input belongs to"
    )
    
    # === OUTPUT RESOURCES (produced by execution) ===
    # These belong to a specific TaskExecution
    task_execution_id: UUID | None = Field(
        foreign_key="task_executions.id", 
        index=True, 
        default=None
    )
    
    # Direction flag
    is_input: bool = Field(default=True, index=True)
    
    # File info
    name: str
    mime_type: str
    file_path: str
    size_bytes: int
    preview_text: str | None = None
    
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    __table_args__ = (
        Index("ix_resources_task_input", "experiment_id", "task_id"),
        Index("ix_resources_execution_output", "task_execution_id"),
    )
```

### 7.5 Agent & Evaluation Tables

```python
# ═══════════════════════════════════════════════════════════════════
# AgentConfig - Worker configuration snapshot (modified)
# ═══════════════════════════════════════════════════════════════════

class AgentRole(str, Enum):
    """Role of an agent in a workflow."""
    WORKER = "worker"
    STAKEHOLDER = "stakeholder"
    MANAGER = "manager"


class AgentConfig(SQLModel, table=True):
    """
    Agent configuration snapshot for a run.
    
    Created by AgentRegistry when execute_task() is called.
    One record per unique worker in the task tree.
    """
    __tablename__ = "agent_configs"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    run_id: UUID = Field(foreign_key="runs.id", index=True)
    
    # Agent identity
    name: str
    agent_type: str  # e.g., "ReactWorker"
    
    # Configuration snapshot
    model: str
    system_prompt: str
    tools: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    
    # Role in workflow
    role: AgentRole = Field(default=AgentRole.WORKER)
    
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    __table_args__ = (
        Index("ix_agent_configs_run", "run_id"),
    )


# ═══════════════════════════════════════════════════════════════════
# TaskEvaluator - Binds evaluators to tasks
# ═══════════════════════════════════════════════════════════════════

class TaskEvaluator(SQLModel, table=True):
    """
    Binds an evaluator (rubric) to a task.
    
    When a task completes, we query this table to find evaluators to run.
    Supports multiple evaluators per task.
    """
    __tablename__ = "task_evaluators"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    run_id: UUID = Field(foreign_key="runs.id", index=True)
    task_id: UUID = Field(index=True)  # References task in the DAG
    
    # Evaluator definition (serialized rubric)
    evaluator_type: str  # "StagedRubric", "MiniF2FRubric", etc.
    evaluator_config: dict = Field(sa_column=Column(JSON))
    
    # Status tracking
    status: str = Field(default="pending", index=True)  # pending → running → completed/failed
    
    # Results (populated after evaluation)
    score: float | None = None
    evaluation_id: UUID | None = Field(foreign_key="evaluations.id", default=None)
    
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    evaluated_at: datetime | None = None
    
    __table_args__ = (
        Index("ix_task_evaluators_run_task", "run_id", "task_id"),
        Index("ix_task_evaluators_status", "status"),
    )
```

### 7.6 Key Queries Enabled

| Query | SQL Pattern |
|-------|-------------|
| What inputs does task X need? | `SELECT * FROM resources WHERE experiment_id=? AND task_id=? AND is_input=True` |
| What did task X produce? | `SELECT * FROM resources WHERE task_execution_id IN (SELECT id FROM task_executions WHERE task_id=?)` |
| What's blocking task X? | `SELECT * FROM task_dependencies WHERE run_id=? AND dependent_task_id=? AND is_satisfied=False` |
| What will unblock when X completes? | `SELECT * FROM task_dependencies WHERE run_id=? AND dependency_task_id=? AND is_satisfied=False` |
| History of task X | `SELECT * FROM task_state_events WHERE run_id=? AND task_id=? ORDER BY timestamp` |
| All currently running tasks | `SELECT * FROM task_executions WHERE status='running'` |
| How many times did task X run? | `SELECT COUNT(*) FROM task_executions WHERE run_id=? AND task_id=?` |
| Tasks with pending evaluations | `SELECT * FROM task_evaluators WHERE status='pending'` |
| Resource lineage for output Y | `SELECT te.*, r.* FROM resources r JOIN task_executions te ON r.task_execution_id=te.id WHERE r.id=?` |

### 7.7 Migration Summary

| Table | Action | Key Changes |
|-------|--------|-------------|
| `experiments` | MODIFY | Add `task_tree`, `root_task_id` |
| `runs` | MODIFY | Remove `task_states` JSON (moved to dedicated tables) |
| `resources` | MODIFY | Add `task_id`, `task_execution_id`, `is_input` |
| `agent_configs` | MODIFY | Add `role` field |
| `task_executions` | CREATE | Track individual task attempts |
| `task_state_events` | CREATE | Event-sourced state history |
| `task_dependencies` | CREATE | Materialized dependency graph |
| `task_evaluators` | CREATE | Bind evaluators to tasks |

---

## Part 8: Implementation Roadmap

### Phase 1: Public API & Restructure (Week 1)

**Goal:** Create clean public API, rename `core/` → `_internal/`

**Files to create:**
- `h_arcane/task.py` (PUBLIC)
- `h_arcane/worker.py` (PUBLIC)
- `h_arcane/runner.py` (PUBLIC - stub initially)

**Tasks:**
- [ ] Create `h_arcane/task.py` with `Task`, `Resource`, `TaskStatus`
- [ ] Create `h_arcane/worker.py` with `BaseWorker` protocol
- [ ] Create `h_arcane/runner.py` with `execute_task()` stub and `ExecutionResult`
- [ ] Rename `h_arcane/core/` → `h_arcane/_internal/`
- [ ] Update all imports in `_internal/` (sed/find-replace)
- [ ] Update `h_arcane/__init__.py` to export from new files
- [ ] Verify: `from h_arcane import Task, execute_task, Resource, BaseWorker` works
- [ ] Write unit tests for `Task` model

### Phase 2: DAG Processing (Week 1)

**Goal:** Implement task tree validation and processing

**Files to create:**
- `h_arcane/_internal/task/__init__.py`
- `h_arcane/_internal/task/registry.py`
- `h_arcane/_internal/task/events.py`

**Tasks:**
- [ ] Create `_internal/task/` directory
- [ ] Implement `TaskRegistry` class in `registry.py`:
  - `_flatten_tree()` - recursive traversal
  - `_resolve_dependencies()` - Task objects → UUIDs
  - `_validate_dag()` - cycle detection (topological sort)
  - `_compute_initial_statuses()` - mark READY tasks
  - `get_ready_tasks()`, `get_dependents()`, `get_task()`
- [ ] Define event constants in `events.py`
- [ ] Write unit tests for DAG validation (cycles, missing deps, etc.)

### Phase 3: Database Updates (Week 1-2)

**Goal:** Add TaskExecution table, update existing models

**Files to modify:**
- `h_arcane/_internal/db/models.py`
- `h_arcane/_internal/db/queries.py`

**Tasks:**
- [ ] Add `TaskExecution` SQLModel table
- [ ] Add `task_tree: JSON` field to `Experiment`
- [ ] Add `task_states: JSON` field to `Run`
- [ ] Add query: `create_task_execution()`
- [ ] Add query: `update_task_status()`
- [ ] Add query: `get_run_with_tasks()`
- [ ] Write migration script (if needed)
- [ ] Test database operations

### Phase 4: Persistence Layer (Week 2)

**Goal:** Convert SDK types to DB records

**Files to create:**
- `h_arcane/_internal/task/persistence.py`

**Tasks:**
- [ ] Implement `serialize_task_tree(task: Task) -> dict`
- [ ] Implement `persist_experiment(session, task) -> Experiment`
- [ ] Implement `persist_run(session, experiment_id, config) -> Run`
- [ ] Implement `persist_input_resources(session, run_id, registry)`
- [ ] Implement `create_resource_from_input(session, inp: Resource)`
- [ ] Handle: file paths, inline content, URLs
- [ ] Implement `wait_for_run_completion(run_id, timeout)`
- [ ] Write unit tests

### Phase 5: Propagation Logic (Week 2)

**Goal:** Task completion triggers dependent tasks

**Files to create:**
- `h_arcane/_internal/task/propagation.py`

**Tasks:**
- [ ] Implement `on_task_completed(run_id, task_id)`:
  - Check dependent tasks
  - Trigger TASK_READY events for ready tasks
  - Propagate to parent composite tasks
- [ ] Implement `propagate_to_parent(run_id, parent_id)`
- [ ] Implement `is_task_ready(run_id, task_id) -> bool`
- [ ] Implement `get_leaf_descendants(task) -> list[Task]`
- [ ] Write integration tests for propagation chains

### Phase 6: Inngest Functions (Week 2-3)

**Goal:** Wire up event-driven execution

**Files to create:**
- `h_arcane/_internal/inngest/__init__.py`
- `h_arcane/_internal/inngest/client.py`
- `h_arcane/_internal/inngest/task_functions.py`
- `h_arcane/_internal/inngest/workflow_functions.py`

**Tasks:**
- [ ] Move Inngest client to `_internal/inngest/client.py`
- [ ] Implement `execute_task` function (triggered by `task/ready`)
- [ ] Implement `propagate_completion` function (triggered by `task/completed`)
- [ ] Implement `workflow_start` function (triggered by `workflow/started`)
- [ ] Implement `workflow_complete` handler
- [ ] Configure concurrency limits (e.g., 15 concurrent tasks)
- [ ] Add timeout and retry policies
- [ ] Update function registry
- [ ] E2E test: simple 3-task DAG

### Phase 7: Complete Runner (Week 3)

**Goal:** Wire up the public `execute_task()` function

**Files to modify:**
- `h_arcane/runner.py` (complete implementation)

**Tasks:**
- [ ] Complete `execute_task()` implementation:
  - Create TaskRegistry
  - Persist to DB
  - Trigger workflow/started event
  - Wait for completion
  - Return ExecutionResult
- [ ] Implement agent assignment strategies:
  - Single agent (default)
  - Factory: `Callable[[Task], Agent]`
  - Mapping: `dict[str, Agent]`
- [ ] Add progress callback (optional)
- [ ] Write integration tests

### Phase 8: Evaluation Integration (Week 3-4)

**Goal:** Support task-level and workflow-level evaluation

**Files to modify:**
- `h_arcane/_internal/evaluation/runner.py`
- `h_arcane/_internal/inngest/task_functions.py`

**Tasks:**
- [ ] On task completion, run `task.evaluator` if set
- [ ] Support `evaluator` param in `execute_task()` for workflow-level eval
- [ ] Aggregate scores across DAG tasks
- [ ] Store results in `TaskExecution.evaluation_details`
- [ ] Connect to existing `StagedRubric` system
- [ ] Write evaluation tests

### Phase 9: Migration & Polish (Week 4)

**Goal:** Migrate existing benchmarks, verify backward compatibility

**Tasks:**
- [ ] Migrate GDPEval loader to use new `Task` schema
- [ ] Migrate MiniF2F loader
- [ ] Migrate ResearchRubrics loader
- [ ] Verify single-task benchmarks still work
- [ ] Create example scripts:
  - `examples/single_task.py`
  - `examples/simple_dag.py`
  - `examples/nested_workflow.py`
- [ ] Performance test with 50+ task DAG
- [ ] Write documentation
- [ ] Update README

### Timeline Summary

| Week | Phases | Deliverable |
|------|--------|-------------|
| 1 | 1, 2, 3 | Public API + DAG validation + DB schema |
| 2 | 4, 5, 6 | Persistence + Propagation + Inngest wiring |
| 3 | 7, 8 | Complete runner + Evaluation |
| 4 | 9 | Migration + Polish + Docs |

---

## Part 9: Open Questions & Future Work

### 9.1 Agent-to-Agent Communication (NOT YET ADDRESSED)

**Gap:** The current plan has no mechanism for agents to communicate with each other during execution.

**Problem areas:**
1. **Stakeholder communications** - How does a worker ping a stakeholder for clarification?
2. **Peer-to-peer messaging** - How do workers on `full_team` coordinate?
3. **Manager delegation** - How does a manager communicate task assignments?

**Current state:** We have no decoupled async messaging pattern. All coordination is implicit through:
- Task completion events (one-way: "I'm done")
- Resource outputs (one-way: "here's my output")

**Possible approaches (to be designed):**

```python
# Option A: Message queue per agent
class CommunicationService
    async def send(self, from_agent: UUID, to_agent: UUID, message: str) -> None
    async def poll(self, agent_id: UUID) -> list[Message]
    async def wait_for_reply(self, message_id: UUID, timeout: float) -> Message

# Option B: Shared "conversation" resources attached to tasks
# Agents read/write to a conversation log for the task they're on

# Option C: Inngest events for agent comms
# task/{task_id}/message → triggers recipient's handler
```

**Key design questions:**
- Should comms be sync (blocking wait for reply) or async (poll inbox)?
- Are messages stored in DB for replay/debugging?
- How does this interact with the action logging we already have?
- Do stakeholders have a different comm pattern (they might be async/batched)?

**TODO:** Design communication protocol before implementing multi-agent workflows.

---

### 9.2 Human Mocks / Human-in-the-Loop (NOT YET PORTED)

**Gap:** ma-gym had "AI worker human mocks" - we haven't ported this concept.

**Original ma-gym feature:**
- Some tasks assigned to simulated humans
- Human mock agents had different behaviors (delays, errors, partial work)

**Interesting new idea (potentially complex):**

Instead of a human seeing one task at a time, model **mental overburdening**:
```python
class HumanWorker(BaseWorker):
    """A worker whose observation includes ALL tasks they're assigned to."""
    
    async def get_observation(self) -> HumanObservation:
        # Return all pending tasks for this human, not just one
        # Models: context switching, priority juggling, overwhelm
        return HumanObservation(
            pending_tasks=await get_all_tasks_for_worker(self.id),
            current_focus=self.current_task_id,
            cognitive_load=len(self.pending_tasks) / self.max_capacity,
        )
```

This could be interesting for studying:
- How agents behave when humans are overloaded
- Multi-tasking patterns and task prioritization
- Realistic human collaboration dynamics

**Concerns:**
- Adds significant complexity to the worker model
- May require different execution patterns (human chooses task order, not DAG)
- Scope creep risk - keep this as future work

**TODO:** Decide if human mocks are in-scope for v1. If yes, design separately.

---

### 9.3 Other Gaps to Address

| Gap | Notes |
|-----|-------|
| **Retry/backoff logic** | Plan mentions retries but no detailed strategy |
| **Timeout handling** | What happens if a task runs forever? |
| **Partial completion** | Can a task be "partially done"? |
| **Dynamic DAG modification** | Can manager add tasks mid-workflow? |
| **Cost tracking** | Token/API costs per task execution |
| **Cancellation** | How to abort a running workflow? |

---

## Appendix A: Comparison with fractal-os

| Concept | fractal-os | h_arcane (new) |
|---------|------------|----------------|
| Task hierarchy | Graph edges (SUBTASK layer) | `children` list on Task |
| Dependencies | Resource edges (INPUT_RESOURCE) | `depends_on` list |
| Status propagation | `propagate_task_completion()` | `on_task_completed()` |
| Ready check | `check_if_task_status_is_ready()` | `is_task_ready()` |
| Task trigger | `trigger_task_if_ready()` | Inngest event dispatch |
| Graph storage | Raphtory (graph DB) | PostgreSQL JSON |

Key simplifications from fractal-os:
1. **No graph database** - Store task tree as JSON, simpler for research use
2. **No real-time UI** - Focus on batch execution for benchmarks
3. **No agent marketplace** - Single agent or factory pattern
4. **No Kanban/status boards** - Terminal-based progress

---

## Appendix B: Example Flow

```python
# User defines workers and tasks:
worker = ReactWorker(model="gpt-4o", tools=[...])

a = Task(name="A", description="...", assigned_to=worker)
b = Task(name="B", description="...", assigned_to=worker, depends_on=[a])
c = Task(name="C", description="...", assigned_to=worker, depends_on=[a])
d = Task(name="D", description="...", assigned_to=worker, depends_on=[b, c])

root = Task(name="Root", description="...", assigned_to=worker, children=[a, b, c, d])
```

```
Initial state:
  A: READY (no deps)
  B: PENDING (needs A)
  C: PENDING (needs A)
  D: PENDING (needs B, C)

A completes:
  → Check B: deps satisfied → READY
  → Check C: deps satisfied → READY
  → B, C execute in parallel

B completes:
  → Check D: needs C → still PENDING

C completes:
  → Check D: B done, C done → READY
  → D executes

D completes:
  → All leaves done → Root COMPLETED
  → Workflow finished
```
