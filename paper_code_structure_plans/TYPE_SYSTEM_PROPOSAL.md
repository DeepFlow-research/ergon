# Type System Proposal: SDK as Source of Truth

## Context

This codebase started as a paper/research codebase for benchmarks (GDPEval, MiniF2F, ResearchRubrics) and is now being extended into a library/SDK. The goal is to make the SDK types the source of truth, with the benchmark infrastructure becoming a consumer of the SDK.

---

## Current State: Two Competing Type Systems

### The SDK Layer (what we WANT)

Located in `h_arcane/core/` and exported from `h_arcane/__init__.py`:

```python
# What users see and import
from h_arcane import Task, Resource, BaseWorker, WorkerContext, WorkerResult, execute_task
```

### The Benchmark Layer (what ACTUALLY runs)

Located in `h_arcane/core/_internal/agents/` and `h_arcane/benchmarks/`:

```python
# Internal types that the system actually uses
from h_arcane.core._internal.agents.base import BaseWorker, WorkerExecutionOutput, BaseToolkit
from h_arcane.benchmarks.common.workers.react_worker import ReActWorker
```

---

## Entity-by-Entity Analysis

### 1. Task

| Aspect | SDK Type | DB Type | Notes |
|--------|----------|---------|-------|
| **Location** | `h_arcane/core/task.py` → `Task` | `h_arcane/core/_internal/db/models.py` → `Experiment` + `TaskExecution` | SDK Task becomes Experiment.task_tree (JSON) |
| **Purpose** | User-facing task definition | Persistence and tracking | |
| **Fields** | `id`, `name`, `description`, `assigned_to`, `children`, `depends_on`, `resources`, `evaluator` | `task_tree` (JSON), `task_states`, per-execution tracking | |

**Current Flow:**
```
SDK Task → serialize_task_tree() → Experiment.task_tree (JSON)
                                 → TaskTreeNode (typed wrapper for JSON)
```

**Status:** ✅ **Good** - SDK Task is source of truth, persistence layer converts correctly.

**Serialized Representation:** `TaskTreeNode` in `schema.py` - typed Pydantic model for the JSON.

---

### 2. Resource

| Aspect | SDK Type | DB Type | Notes |
|--------|----------|---------|-------|
| **Location** | `h_arcane/core/task.py` → `Resource` | `h_arcane/core/_internal/db/models.py` → `ResourceRecord` | Intentionally different names |
| **Purpose** | User-facing input definition | Storage with metadata | |
| **Fields** | `path`, `name`, `content`, `url`, `mime_type` | `id`, `experiment_id`, `run_id`, `task_id`, `file_path`, `size_bytes`, `preview_text`, etc. | |

**Current Flow:**
```
SDK Resource → create_resource_from_sdk() → ResourceRecord (DB)
            → persist to disk if content/url
```

**Status:** ✅ **Good** - SDK Resource is source of truth, persistence converts correctly.

**Serialized Representation:** `ResourceRef` in `schema.py` - for task_tree JSON.

---

### 3. Worker ⚠️ **PROBLEM AREA**

| Aspect | SDK Type | Internal Type | Benchmark Implementation |
|--------|----------|---------------|-------------------------|
| **Location** | `h_arcane/core/worker.py` | `h_arcane/core/_internal/agents/base.py` | `h_arcane/benchmarks/common/workers/react_worker.py` |
| **Class** | `BaseWorker` (Protocol) | `BaseWorker` (Protocol) - DIFFERENT | `ReActWorker` (class) |
| **Properties** | `id`, `name`, `model`, `tools`, `system_prompt` | None required | Via `WorkerConfig` |
| **Execute signature** | `execute(task: Task, context: WorkerContext) → WorkerResult` | `execute(run_id, task_description, input_resources, toolkit) → WorkerExecutionOutput` | Internal signature |

**Current Flow:**
```
SDK BaseWorker (documented)     →  Users implement this
        ↓
store_workers_from_task()       →  Stores in memory with SDK type hints
        ↓
worker_execute_fn               →  get_worker() returns "SDK BaseWorker"
        ↓
worker.execute(run_id, ...)     →  CALLS WITH INTERNAL SIGNATURE! 🔴
        ↓
ReActWorker                     →  Implements INTERNAL signature
```

**Status:** ❌ **Broken** - Two incompatible protocols with the same name. SDK types are lies.

---

### 4. WorkerContext

| Aspect | SDK Type | Internal Type |
|--------|----------|---------------|
| **Location** | `h_arcane/core/worker.py` | `h_arcane/benchmarks/common/workers/react_worker.py` |
| **Class** | `WorkerContext` | `WorkerContext` - DIFFERENT |
| **Fields** | `run_id`, `task_id`, `sandbox`, `input_resources: list[Resource]`, `metadata` | `run_id`, `num_executed_tools`, `model_name` |

**Status:** ❌ **Broken** - Two classes with same name, different purposes.

---

### 5. WorkerResult / WorkerExecutionOutput

| Aspect | SDK Type | Internal Type |
|--------|----------|---------------|
| **Location** | `h_arcane/core/worker.py` | `h_arcane/core/_internal/agents/base.py` |
| **Class** | `WorkerResult` | `WorkerExecutionOutput` |
| **Fields** | `success`, `actions: list[Action]`, `outputs: list[Resource]`, `output_text`, `reasoning`, `error` | `reasoning`, `output_text`, `output_resource_ids: list[str]` |

**Status:** ⚠️ **Misaligned** - Different return types from worker execution.

**Key Insight:** WorkerResult should be the return type for trace data. The worker collects what happened during execution (actions, Q&A, outputs) and returns it. The execution layer then persists this data with run_id. The worker does NOT need run_id during execution - only at persistence time.

---

### 6. Toolkit / Stakeholder

| Aspect | SDK | Benchmark |
|--------|-----|-----------|
| **Location** | Not in SDK | `h_arcane/core/_internal/agents/base.py` |
| **Purpose** | - | Bundles tools + stakeholder access |
| **Used by** | - | `ReActWorker` (internal detail) |

**Status:** ✅ **Intentionally NOT in SDK** - Toolkit is an implementation detail of specific worker implementations (like ReActWorker), NOT part of the BaseWorker protocol. Not all workers need a toolkit - a simple LLM-only worker has no tools.

**Key Insight:** Toolkit should NOT be part of the BaseWorker protocol. It's an internal attribute of ReActWorker that gets configured before execution. The SDK protocol should remain minimal and not assume all workers need toolkits.

---

### 7. SandboxManager

| Aspect | Current | Proposed |
|--------|---------|----------|
| **Key** | `run_id` | `task_id` |
| **Why** | Legacy from paper codebase | Task is the execution context, not run |

**Key Insight:** Sandbox should be keyed by `task_id`, not `run_id` or `worker_id`:
- **worker_id is wrong** because: same worker on different tasks would share sandbox (state leakage), different workers on same task get different sandboxes (but they should share)
- **run_id is wrong** because: it couples sandbox lifecycle to the entire workflow, not the task
- **task_id is correct** because: each task gets isolated environment, multiple workers on same task share the sandbox (working on same files)

---

## Proposed Architecture

### Core Design Principles

1. **SDK Types are Source of Truth** - `BaseWorker`, `WorkerContext`, `WorkerResult` are the contract
2. **Toolkit is NOT part of protocol** - it's an internal implementation detail of specific workers
3. **run_id only needed at persistence** - worker doesn't need it during execution
4. **Worker returns trace data** - execution layer persists it with run_id
5. **Sandbox keyed by task_id** - each task gets its own isolated execution environment

### Principle: SDK Types are Source of Truth

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           SDK LAYER (Source of Truth)                        │
│                                                                             │
│   h_arcane/                                                                 │
│   ├── __init__.py          # Public exports                                 │
│   └── core/                                                                 │
│       ├── task.py          # Task, Resource, TaskStatus                     │
│       ├── worker.py        # BaseWorker, WorkerContext, WorkerResult        │
│       └── runner.py        # execute_task(), ExecutionResult                │
│                                                                             │
│   BaseWorker Protocol (MINIMAL - no toolkit requirement):                   │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │ @runtime_checkable                                                   │   │
│   │ class BaseWorker(Protocol):                                          │   │
│   │     id: UUID                                                        │   │
│   │     name: str                                                       │   │
│   │     model: str                                                      │   │
│   │     tools: list[Tool]  # Can be empty for simple workers            │   │
│   │     system_prompt: str                                              │   │
│   │                                                                      │   │
│   │     async def execute(self, task: Task, context: WorkerContext)     │   │
│   │         -> WorkerResult: ...                                        │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   WorkerResult (includes trace data for persistence):                       │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │ class WorkerResult(BaseModel):                                       │   │
│   │     success: bool                                                   │   │
│   │     output_text: str | None = None                                  │   │
│   │     reasoning: str | None = None                                    │   │
│   │     error: str | None = None                                        │   │
│   │                                                                      │   │
│   │     # Trace data - worker populates, execution layer persists       │   │
│   │     actions: list[Action] = []           # Tool calls made          │   │
│   │     qa_exchanges: list[QAExchange] = []  # Stakeholder Q&A          │   │
│   │     outputs: list[Resource] = []         # Files created            │   │
│   │                                                                      │   │
│   │     # Optional metadata                                             │   │
│   │     tokens_used: int | None = None                                  │   │
│   │     cost_usd: float | None = None                                   │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   User code (simple worker - no toolkit needed):                            │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │ class SimpleWorker:                                                  │   │
│   │     id: UUID                                                        │   │
│   │     name: str = "simple_worker"                                     │   │
│   │     model: str                                                      │   │
│   │     tools: list = []  # Empty - no tools!                           │   │
│   │     system_prompt: str                                              │   │
│   │                                                                      │   │
│   │     async def execute(self, task: Task, context: WorkerContext):    │   │
│   │         response = await call_llm(self.model, task.description)     │   │
│   │         return WorkerResult(                                        │   │
│   │             success=True,                                           │   │
│   │             output_text=response,                                   │   │
│   │             actions=[],  # No tools used                            │   │
│   │         )                                                           │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     │ Adapts SDK types for execution
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        EXECUTION LAYER (Adapter)                             │
│                                                                             │
│   h_arcane/core/_internal/task/                                             │
│   ├── worker_execute.py    # Adapts SDK worker to execution environment     │
│   ├── persistence.py       # SDK → DB conversion                            │
│   └── schema.py            # TaskTreeNode, WorkerRef (serialization)        │
│                                                                             │
│   SandboxManager (keyed by task_id):                                        │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │ class BaseSandboxManager:                                            │   │
│   │     _sandboxes: dict[UUID, AsyncSandbox] = {}  # task_id -> sandbox │   │
│   │                                                                      │   │
│   │     async def get_or_create(self, task_id: UUID) -> AsyncSandbox:   │   │
│   │         if task_id not in self._sandboxes:                          │   │
│   │             self._sandboxes[task_id] = await AsyncSandbox.create()  │   │
│   │         return self._sandboxes[task_id]                             │   │
│   │                                                                      │   │
│   │     async def run_skill(self, task_id: UUID, skill_name: str, ...)  │   │
│   │         -> T:                                                       │   │
│   │         sandbox = self._sandboxes[task_id]                          │   │
│   │         ...                                                         │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   worker_execute_fn does:                                                   │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │ # Get SDK worker from storage                                        │   │
│   │ worker: BaseWorker = get_worker(task_id)                            │   │
│   │                                                                      │   │
│   │ # Configure worker if it's a benchmark worker (has toolkit needs)   │   │
│   │ if hasattr(worker, 'configure_for_execution'):                      │   │
│   │     toolkit = create_toolkit(worker.id, stakeholder, sandbox_mgr)   │   │
│   │     worker.configure_for_execution(toolkit)                         │   │
│   │                                                                      │   │
│   │ # Build SDK context - sandbox keyed by task_id                      │   │
│   │ context = WorkerContext(                                            │   │
│   │     task_id=task_id,                                                │   │
│   │     run_id=run_id,  # For observability only                        │   │
│   │     sandbox=sandbox_manager.get_or_create(task_id),  # BY TASK_ID   │   │
│   │     input_resources=convert_db_to_sdk_resources(db_resources),      │   │
│   │     parent_outputs=parent_task_outputs,                             │   │
│   │ )                                                                   │   │
│   │                                                                      │   │
│   │ # Reconstruct minimal Task                                          │   │
│   │ task = Task(name=..., description=..., assigned_to=worker, ...)     │   │
│   │                                                                      │   │
│   │ # Call SDK worker - returns trace data in result                    │   │
│   │ result: WorkerResult = await worker.execute(task, context)          │   │
│   │                                                                      │   │
│   │ # NOW persist with run_id - this is where we need it                │   │
│   │ for action in result.actions:                                       │   │
│   │     action.run_id = run_id                                          │   │
│   │     action.agent_id = agent_config_id                               │   │
│   │     queries.actions.create(action)                                  │   │
│   │                                                                      │   │
│   │ for qa in result.qa_exchanges:                                      │   │
│   │     persist_message(run_id, experiment_id, qa)                      │   │
│   │                                                                      │   │
│   │ persist_outputs(run_id, task_id, result.outputs)                    │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     │ Persists to database
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         DATABASE LAYER (Storage)                             │
│                                                                             │
│   h_arcane/core/_internal/db/models.py                                      │
│   ├── Experiment       # Stores task_tree as JSON                           │
│   ├── Run              # Execution state, task_states                       │
│   ├── TaskExecution    # Per-task execution tracking                        │
│   ├── ResourceRecord   # File resources                                     │
│   ├── Action           # Tool call trace                                    │
│   └── AgentConfig      # Worker config snapshot                             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     │ Benchmark workers use SDK
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      BENCHMARK LAYER (SDK Consumer)                          │
│                                                                             │
│   h_arcane/benchmarks/                                                      │
│   ├── common/workers/                                                       │
│   │   └── react_worker.py  # ReActWorker implements SDK BaseWorker          │
│   │                                                                         │
│   ├── gdpeval/                                                              │
│   │   ├── toolkit.py       # GDPEvalToolkit (INTERNAL to ReActWorker)       │
│   │   └── stakeholder.py   # GDPEvalStakeholder                             │
│   │                                                                         │
│   Toolkit (uses worker.id, NOT run_id):                                     │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │ class GDPEvalToolkit(BaseToolkit):                                   │   │
│   │     def __init__(                                                   │   │
│   │         self,                                                       │   │
│   │         worker_id: UUID,  # NOT run_id - we don't have it yet       │   │
│   │         stakeholder: BaseStakeholder,                               │   │
│   │         sandbox_manager: BaseSandboxManager,                        │   │
│   │         max_questions: int = 10,                                    │   │
│   │     ):                                                              │   │
│   │         self.worker_id = worker_id                                  │   │
│   │         self.stakeholder = stakeholder                              │   │
│   │         self.sandbox_manager = sandbox_manager                      │   │
│   │         self._qa_history: list[QAExchange] = []  # Accumulate       │   │
│   │                                                                      │   │
│   │     async def ask_stakeholder(self, question: str) -> str:          │   │
│   │         answer = await self.stakeholder.answer(question)            │   │
│   │         self._qa_history.append(QAExchange(q=question, a=answer))   │   │
│   │         return answer                                               │   │
│   │                                                                      │   │
│   │     def get_qa_history(self) -> list[QAExchange]:                   │   │
│   │         """Called by worker to include in WorkerResult."""          │   │
│   │         return self._qa_history                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ReActWorker (toolkit is INTERNAL, not part of protocol):                  │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │ class ReActWorker:                                                   │   │
│   │     """Benchmark worker with toolkit support."""                    │   │
│   │                                                                      │   │
│   │     # SDK BaseWorker required properties                            │   │
│   │     id: UUID                                                        │   │
│   │     name: str                                                       │   │
│   │     model: str                                                      │   │
│   │     tools: list[Tool]                                               │   │
│   │     system_prompt: str                                              │   │
│   │                                                                      │   │
│   │     # INTERNAL - NOT part of protocol                               │   │
│   │     _config: WorkerConfig                                           │   │
│   │     _toolkit: BaseToolkit | None = None                             │   │
│   │                                                                      │   │
│   │     def __init__(self, model: str, config: WorkerConfig):           │   │
│   │         self.id = uuid4()                                           │   │
│   │         self.name = config.name or "react_worker"                   │   │
│   │         self.model = model                                          │   │
│   │         self.system_prompt = config.system_prompt                   │   │
│   │         self._config = config                                       │   │
│   │         self.tools = []  # Empty until toolkit configured           │   │
│   │                                                                      │   │
│   │     def configure_for_execution(self, toolkit: BaseToolkit):        │   │
│   │         """Called by execution layer before execute()."""           │   │
│   │         self._toolkit = toolkit                                     │   │
│   │         self.tools = toolkit.get_tools()                            │   │
│   │                                                                      │   │
│   │     async def execute(self, task: Task, context: WorkerContext)     │   │
│   │         -> WorkerResult:                                            │   │
│   │         # Use self._toolkit internally                              │   │
│   │         # Collect trace data during execution                       │   │
│   │         actions = []                                                │   │
│   │         # ... run agent ...                                         │   │
│   │                                                                      │   │
│   │         # Return result WITH trace data                             │   │
│   │         return WorkerResult(                                        │   │
│   │             success=True,                                           │   │
│   │             output_text=result.output_text,                         │   │
│   │             reasoning=result.reasoning,                             │   │
│   │             actions=actions,  # Execution layer persists these      │   │
│   │             qa_exchanges=self._toolkit.get_qa_history()             │   │
│   │                 if self._toolkit else [],                           │   │
│   │         )                                                           │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Changes Required

### 1. Update `worker_execute_fn` to Use SDK Types

**Current:**
```python
worker = get_worker(task_id)
exec_out = await worker.execute(
    run_id=run_id,
    task_description=payload.task_description,
    input_resources=input_resources,  # DB ResourceRecord
    toolkit=toolkit,
)
```

**Proposed:**
```python
worker = get_worker(task_id)  # SDK BaseWorker

# Configure worker if it has toolkit needs (benchmark workers)
if hasattr(worker, 'configure_for_execution'):
    # Create toolkit with worker.id (NOT run_id - we may not have it yet)
    toolkit = toolkit_factory(
        worker_id=worker.id,  # Use worker.id, not run_id
        stakeholder=stakeholder,
        sandbox_manager=sandbox_manager,
        max_questions=max_questions,
    )
    worker.configure_for_execution(toolkit)

# Build SDK WorkerContext - sandbox keyed by task_id
sdk_resources = [convert_to_sdk_resource(r) for r in input_resources]
context = WorkerContext(
    task_id=task_id,
    run_id=run_id,  # For observability only, not required for execution
    sandbox=sandbox_manager.get_or_create(task_id),  # KEYED BY TASK_ID
    input_resources=sdk_resources,
    parent_outputs=parent_task_outputs,
)

# Reconstruct minimal Task for worker
task = Task(
    id=UUID(task_id),
    name=task_node.name,
    description=task_node.description,
    assigned_to=worker,
    resources=sdk_resources,
)

# Call with SDK signature - worker returns trace data
result: WorkerResult = await worker.execute(task, context)

# NOW persist with run_id - this is the only place we need it
for action in result.actions:
    action.run_id = run_id
    action.agent_id = agent_config_id
    queries.actions.create(action)

for qa in result.qa_exchanges:
    persist_message(run_id, experiment_id, qa)

if result.outputs:
    persist_output_resources(run_id, task_id, execution_id, result.outputs)
```

### 2. Update `ReActWorker` to Implement SDK `BaseWorker`

**Current:**
```python
class ReActWorker:
    def __init__(self, model: str, config: WorkerConfig):
        self.model = model
        self.config = config

    async def execute(
        self,
        run_id: UUID,
        task_description: str,
        input_resources: list[ResourceRecord],
        toolkit: BaseToolkit,
    ) -> WorkerExecutionOutput:
        ...
```

**Proposed:**
```python
class ReActWorker:
    """Benchmark worker with toolkit support. Implements SDK BaseWorker protocol."""
    
    # SDK BaseWorker required properties
    id: UUID
    name: str
    model: str
    tools: list[Tool]
    system_prompt: str
    
    # INTERNAL - NOT part of protocol
    _config: WorkerConfig
    _toolkit: BaseToolkit | None = None
    
    def __init__(self, model: str, config: WorkerConfig):
        self.id = uuid4()
        self.name = config.name or "react_worker"
        self.model = model
        self.system_prompt = config.system_prompt
        self._config = config
        self.tools = []  # Empty until toolkit configured
    
    def configure_for_execution(self, toolkit: BaseToolkit):
        """Called by execution layer before execute(). NOT part of protocol."""
        self._toolkit = toolkit
        self.tools = toolkit.get_tools()

    async def execute(
        self,
        task: Task,
        context: WorkerContext,
    ) -> WorkerResult:
        """Execute task using SDK types. Returns trace data for persistence."""
        
        if self._toolkit is None:
            raise ValueError("ReActWorker requires toolkit - call configure_for_execution() first")
        
        # Run agent
        agent = Agent(
            name=self.name,
            model=self.model,
            instructions=self.system_prompt,
            tools=[as_step(t) for t in self.tools],
        )
        
        result = await Runner.run(agent, task.description, max_turns=25)
        
        # Collect trace data - execution layer will persist with run_id
        actions = extract_actions_from_result(result)
        
        return WorkerResult(
            success=True,
            output_text=result.final_output.output_text,
            reasoning=result.final_output.reasoning,
            actions=actions,  # Execution layer persists these with run_id
            qa_exchanges=self._toolkit.get_qa_history(),  # Same
            outputs=[],  # Benchmark outputs tracked via sandbox
        )
```

### 3. Remove Duplicate `BaseWorker` from Internal

**Delete or rename:**
- `h_arcane/core/_internal/agents/base.py` → `BaseWorker` protocol

**Keep:**
- `BaseToolkit` - still useful internally
- `BaseStakeholder` - still useful internally
- `WorkerExecutionOutput` → Rename to `AgentOutput` or merge into `WorkerResult`

### 4. Remove Duplicate `WorkerContext` from Benchmark

**Delete:**
- `h_arcane/benchmarks/common/workers/react_worker.py` → `WorkerContext` class

**Use:**
- `h_arcane/core/worker.py` → `WorkerContext` everywhere

### 5. Add Conversion Utilities

```python
# h_arcane/core/_internal/task/conversions.py

def db_resource_to_sdk(db_resource: ResourceRecord) -> Resource:
    """Convert DB ResourceRecord to SDK Resource."""
    return Resource(
        path=db_resource.file_path,
        name=db_resource.name,
        mime_type=db_resource.mime_type,
    )

def sdk_resource_to_db(
    sdk_resource: Resource,
    run_id: UUID,
    task_id: UUID,
    is_input: bool = False,
) -> dict:
    """Convert SDK Resource to DB ResourceRecord dict."""
    ...
```

---

## Summary of Type Ownership

| Type | Source of Truth | DB Representation | Notes |
|------|----------------|-------------------|-------|
| `Task` | `h_arcane/core/task.py` | `Experiment.task_tree` (JSON) | Serialized via `TaskTreeNode` |
| `Resource` | `h_arcane/core/task.py` | `ResourceRecord` table | Converted by `create_resource_from_sdk()` |
| `BaseWorker` | `h_arcane/core/worker.py` | `AgentConfig` table | Worker config snapshot |
| `WorkerContext` | `h_arcane/core/worker.py` | N/A (runtime only) | Built by execution layer |
| `WorkerResult` | `h_arcane/core/worker.py` | `Action` + `ResourceRecord` | Worker returns trace data, execution layer persists |
| `TaskStatus` | `h_arcane/core/task.py` | `TaskStatus` enum in `db/models.py` | Duplicated (intentional, same values) |
| `Toolkit` | `h_arcane/benchmarks/*/toolkit.py` | N/A (internal) | **NOT part of SDK protocol** - internal to specific workers |
| `Sandbox` | `h_arcane/core/_internal/infrastructure/sandbox.py` | N/A (runtime only) | **Keyed by task_id**, not run_id or worker_id |

### Key Design Decisions

| Concern | Decision | Rationale |
|---------|----------|-----------|
| Toolkit in BaseWorker | **NO** | Not all workers need toolkits. It's an implementation detail of ReActWorker. |
| run_id in worker.execute() | **NO** | SDK protocol is clean. Execution layer passes run_id to toolkit separately. |
| Toolkit has run_id | **YES** | Execution layer creates toolkit with run_id for CommunicationService. |
| Sandbox key | **task_id** | Each task gets its own isolated environment. Multiple workers on same task share it. |
| Action persistence | **Execution layer** | `tracing.py` extracts actions, execution layer adds run_id and persists. |
| Q&A persistence | **Toolkit (immediate)** | CommunicationService needs run_id for thread management. Toolkit has it. |

---

## Migration Path

### Phase 1: Update Execution Infrastructure (Non-Breaking)
1. Add conversion utilities (`conversions.py`) - `db_resource_to_sdk()`, etc.
2. Update `BaseSandboxManager` to key by `task_id` instead of `run_id`
3. Update `worker_execute_fn` to build SDK `WorkerContext` with sandbox by `task_id`
4. Add `configure_for_execution()` check in `worker_execute_fn`

### Phase 2: Update Toolkits
1. Update toolkit factories to accept `task_id` in addition to `run_id`:
   - `create_toolkit(task_id, run_id, experiment_id, stakeholder, sandbox_manager, ...)`
2. Update `GDPEvalToolkit`, `MiniF2FToolkit`, etc. to:
   - Accept `task_id` for sandbox keying
   - Keep `run_id`/`experiment_id` for CommunicationService (already works)
   - Change `sandbox_manager.run_skill(self.run_id, ...)` → `sandbox_manager.run_skill(self.task_id, ...)`
   - Add `get_qa_history()` method for WorkerResult
3. Update sandbox manager methods to use `task_id` as key

### Phase 3: Update ReActWorker
1. Add `configure_for_execution(toolkit)` method
2. Change `execute()` to return trace data in `WorkerResult`
3. Remove direct persistence from worker - execution layer handles it
4. Remove `run_id` from worker's concerns entirely

### Phase 4: Update Tracing and Persistence
1. Refactor `h_arcane/benchmarks/common/workers/tracing.py`:
   - Split `log_actions_from_result()` into:
     - `extract_actions_from_result(result, model_name)` → returns `list[Action]` without run_id
     - Execution layer adds `run_id`/`agent_id` and calls `queries.actions.create()`
   - This keeps action extraction logic in tracing.py but moves persistence to execution layer

2. Update `worker_execute_fn` to persist trace data from `WorkerResult`:
   - Extract actions: `actions = extract_actions_from_result(runner_result, model_name)`
   - Add IDs and persist: `for action in actions: action.run_id = run_id; queries.actions.create(action)`
   - Q&A already persisted by toolkit's CommunicationService (toolkit has run_id)
   - Persist `result.outputs` with `run_id`/`task_id`

### Phase 5: Clean Up Internal Types
1. Remove duplicate `BaseWorker` from `_internal/agents/base.py`
2. Remove duplicate `WorkerContext` from `react_worker.py`
3. Rename `WorkerExecutionOutput` → `AgentOutput` or remove

### Phase 6: Documentation
1. Update docstrings to reflect SDK-first design
2. Add examples of custom worker implementations
3. Document benchmark workers as reference implementations

---

## Benchmark System Changes

### Current Benchmark Flow (Problematic)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1. User calls load_gdpeval_task(task_id, worker)                            │
│                                                                             │
│    - Creates Task with SDK Resources                                        │
│    - Worker is passed in BUT NOT CONFIGURED with toolkit/stakeholder        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 2. User calls execute_task(task)                                            │
│                                                                             │
│    - Stores worker in memory via store_workers_from_task()                  │
│    - Persists Task → Experiment.task_tree                                   │
│    - Triggers workflow/started Inngest event                                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 3. worker_execute_fn runs (Inngest)                                         │
│                                                                             │
│    - Looks up benchmark_name from Experiment                                │
│    - Uses registry to get factories:                                        │
│        sandbox_manager = get_sandbox_manager(benchmark_name)                │
│        stakeholder = get_stakeholder_factory(benchmark_name)(experiment)    │
│        toolkit = get_toolkit_factory(benchmark_name)(run_id, ...)           │
│                                                                             │
│    - Gets worker from memory: worker = get_worker(task_id)                  │
│                                                                             │
│    - 🔴 CALLS WITH INTERNAL SIGNATURE:                                      │
│        worker.execute(run_id, task_description, input_resources, toolkit)   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Problems:**
1. Worker is created BEFORE toolkit/stakeholder exist
2. Toolkit/stakeholder are created at execution time based on `benchmark_name` lookup
3. Worker doesn't know about toolkit until execute() is called
4. The registry-based factory pattern couples worker execution to benchmark infrastructure

### Proposed Benchmark Flow (RECOMMENDED)

**Key Insight:** Toolkit doesn't need `run_id` - it only needs `worker_id` for internal tracking. Persistence with `run_id` happens AFTER worker execution, in the execution layer.

```python
# worker_execute_fn - updated with new design
async def worker_execute_fn(ctx: inngest.Context) -> WorkerExecuteResult:
    # ... load run, experiment, resources ...
    
    worker = get_worker(task_id)  # SDK BaseWorker
    
    # Configure worker if it has toolkit needs (benchmark workers)
    if hasattr(worker, 'configure_for_execution'):
        sandbox_manager = get_sandbox_manager(benchmark_name)
        stakeholder = stakeholder_factory(experiment)
        
        # Create toolkit with worker.id (NOT run_id!)
        toolkit = toolkit_factory(
            worker_id=worker.id,  # Use worker.id, not run_id
            stakeholder=stakeholder,
            sandbox_manager=sandbox_manager,
            max_questions=max_questions,
        )
        worker.configure_for_execution(toolkit)
    
    # Build SDK WorkerContext - sandbox keyed by task_id
    sdk_resources = [db_resource_to_sdk(r) for r in input_resources]
    context = WorkerContext(
        task_id=task_id,
        run_id=run_id,  # For observability only
        sandbox=sandbox_manager.get_or_create(task_id),  # KEYED BY TASK_ID
        input_resources=sdk_resources,
        parent_outputs=parent_task_outputs,
    )
    
    # Build minimal Task
    task = Task(
        id=UUID(task_id),
        name=task_node.name,
        description=payload.task_description,
        assigned_to=worker,
        resources=sdk_resources,
    )
    
    # Call with SDK signature - worker returns trace data
    result: WorkerResult = await worker.execute(task, context)
    
    # NOW persist with run_id - this is where we need it
    for action in result.actions:
        action.run_id = run_id
        action.agent_id = agent_config_id
        queries.actions.create(action)
    
    for qa in result.qa_exchanges:
        persist_message(run_id, experiment_id, qa)
    
    if result.outputs:
        persist_output_resources(run_id, task_id, execution_id, result.outputs)
    
    return WorkerExecuteResult(...)
```

```python
# ReActWorker - toolkit is INTERNAL, not part of protocol
class ReActWorker:
    """Benchmark worker with toolkit support. Implements SDK BaseWorker."""
    
    # SDK BaseWorker required properties
    id: UUID
    name: str
    model: str
    tools: list[Tool]
    system_prompt: str
    
    # INTERNAL - NOT part of protocol
    _config: WorkerConfig
    _toolkit: BaseToolkit | None = None
    
    def __init__(self, model: str, config: WorkerConfig):
        self.id = uuid4()
        self.name = config.name or "react_worker"
        self.model = model
        self.system_prompt = config.system_prompt
        self._config = config
        self.tools = []  # Empty until toolkit configured
    
    def configure_for_execution(self, toolkit: BaseToolkit):
        """Called by execution layer before execute(). NOT part of protocol."""
        self._toolkit = toolkit
        self.tools = toolkit.get_tools()
    
    async def execute(self, task: Task, context: WorkerContext) -> WorkerResult:
        if self._toolkit is None:
            raise ValueError("ReActWorker requires toolkit - call configure_for_execution() first")
        
        # Run agent with OpenAI Agents SDK
        agent = Agent(
            name=self.name,
            model=self.model,
            instructions=self.system_prompt,
            tools=[as_step(t) for t in self.tools],
        )
        
        task_prompt = self._format_task(task.description, context.input_resources)
        result = await Runner.run(agent, task_prompt, max_turns=25)
        
        # Collect trace data - DON'T persist here, return for execution layer
        actions = extract_actions_from_result(result)
        
        # Return trace data in result - execution layer persists with run_id
        return WorkerResult(
            success=True,
            output_text=result.final_output.output_text,
            reasoning=result.final_output.reasoning,
            actions=actions,  # Execution layer adds run_id and persists
            qa_exchanges=self._toolkit.get_qa_history(),  # Same
            outputs=[],  # Tracked via sandbox
        )
```

```python
# Toolkit - created by execution layer, which HAS run_id
# The key insight: worker.execute() doesn't need run_id in its signature,
# but toolkit (created by execution layer) can have it for internal persistence
class GDPEvalToolkit(BaseToolkit):
    def __init__(
        self,
        task_id: UUID,       # For sandbox keying
        run_id: UUID,        # For communication service (execution layer provides this)
        experiment_id: UUID, # For communication service
        stakeholder: BaseStakeholder,
        sandbox_manager: BaseSandboxManager,
        max_questions: int = 10,
    ):
        self.task_id = task_id
        self.run_id = run_id
        self.experiment_id = experiment_id
        self.stakeholder = stakeholder
        self.sandbox_manager = sandbox_manager
        self.max_questions = max_questions
        self._qa_history: list[QAExchange] = []
    
    async def ask_stakeholder(self, question: str) -> str:
        answer = await self.stakeholder.answer(question)
        self._qa_history.append(QAExchange(question=question, answer=answer))
        # CommunicationService still persists immediately (for thread management)
        # This is fine - toolkit has run_id from execution layer
        communication_service.save_message(...)
        return answer
    
    def get_qa_history(self) -> list[QAExchange]:
        """Return Q&A history for WorkerResult."""
        return self._qa_history
    
    # Tool methods use task_id for sandbox, not run_id
    async def _run_skill(self, skill_name: str, response_type, **kwargs):
        return await self.sandbox_manager.run_skill(
            self.task_id,  # CHANGED: was run_id
            skill_name,
            response_type,
            **kwargs,
        )
```

```python
# SandboxManager - keyed by task_id, NOT run_id or worker_id
class BaseSandboxManager:
    _sandboxes: dict[UUID, AsyncSandbox] = {}  # task_id -> sandbox
    
    async def get_or_create(self, task_id: UUID, ...) -> AsyncSandbox:
        if task_id not in self._sandboxes:
            self._sandboxes[task_id] = await AsyncSandbox.create(...)
        return self._sandboxes[task_id]
    
    async def run_skill(self, task_id: UUID, skill_name: str, ...) -> T:
        sandbox = self._sandboxes[task_id]
        ...
```

**Why This Works:**

| What | Key/ID | Why |
|------|--------|-----|
| Sandbox | `task_id` | Each task gets isolated environment. Multiple workers share it. |
| Toolkit | Has `run_id` + `task_id` | Gets them from execution layer (which has them). Toolkit is internal. |
| CommunicationService | `run_id` | Thread management requires run_id. Toolkit persists Q&A immediately. |
| Actions | Extracted, then `run_id` added | `tracing.py` extracts actions, execution layer adds run_id and persists. |

**Key Insight:** The worker's `execute()` method doesn't need `run_id` in its signature. The execution layer (which HAS `run_id`) creates the toolkit with it. This keeps the SDK protocol clean while letting benchmark workers use `run_id` internally.

**Benefits:**
1. SDK `BaseWorker` protocol is clean - no `run_id` in signature
2. Execution layer controls toolkit creation with proper IDs
3. Sandbox isolation is per-task, not per-run
4. Actions extracted separately, persisted with `run_id` by execution layer

---

### Recommended Migration Approach

**Phase 1: Update Execution Layer (Non-Breaking)**
- Add `configure_for_execution()` check in `worker_execute_fn`
- Update toolkit factories to accept `worker_id` instead of `run_id`
- Update sandbox manager to key by `task_id`
- Worker returns trace data in `WorkerResult`, execution layer persists

**Phase 2: Update ReActWorker**
- Add `configure_for_execution()` method
- Change `execute()` to return trace data instead of persisting directly
- Remove `run_id` from worker's concerns

**Phase 3: Update Toolkit Implementations**
- Change `GDPEvalToolkit.__init__` to accept `worker_id` instead of `run_id`
- Accumulate Q&A history instead of persisting immediately
- Add `get_qa_history()` method

**Phase 4: Introduce Benchmark-Specific Worker Classes (Optional)**
- `GDPEvalWorker(ReActWorker)` - knows about GDPEval toolkit config
- `MiniF2FWorker(ReActWorker)` - knows about MiniF2F toolkit config
- Cleaner loaders - users don't configure workers manually

### Updated Benchmark Registry

```python
# h_arcane/benchmarks/registry.py - after migration

from h_arcane.benchmarks.enums import BenchmarkName
from h_arcane.benchmarks.gdpeval.worker import GDPEvalWorker
from h_arcane.benchmarks.minif2f.worker import MiniF2FWorker
from h_arcane.benchmarks.researchrubrics.worker import ResearchRubricsWorker

BENCHMARK_WORKERS: dict[BenchmarkName, type] = {
    BenchmarkName.GDPEVAL: GDPEvalWorker,
    BenchmarkName.MINIF2F: MiniF2FWorker,
    BenchmarkName.RESEARCHRUBRICS: ResearchRubricsWorker,
}

def get_worker_class(benchmark_name: BenchmarkName) -> type:
    """Get the worker class for a benchmark."""
    return BENCHMARK_WORKERS[benchmark_name]
```

### Updated Loader Functions

```python
# h_arcane/benchmarks/gdpeval/loader.py - after migration

def load_gdpeval_task(
    task_id: str,
    model: str = "gpt-4o",  # No longer need to pass worker instance
) -> Task:
    """Load a GDPEval task with appropriate worker."""
    # ... load rubric, description, resources ...
    
    # Create GDPEval-specific worker
    worker = GDPEvalWorker(model=model)
    
    return Task(
        name=task_id,
        description=task_description,
        assigned_to=worker,
        resources=resources,
        evaluator=staged_rubric.rubric,
    )
```

This is cleaner - users don't need to manually create ReActWorker with the right config.

### Files to Change for Benchmark Migration

| File | Change |
|------|--------|
| `h_arcane/benchmarks/common/workers/react_worker.py` | Add `configure_for_execution()`, return trace data in `WorkerResult` |
| `h_arcane/benchmarks/common/workers/tracing.py` | Split `log_actions_from_result()` → `extract_actions_from_result()` |
| `h_arcane/benchmarks/gdpeval/toolkit.py` | Add `task_id`, change `run_skill(run_id)` → `run_skill(task_id)`, add `get_qa_history()` |
| `h_arcane/benchmarks/minif2f/toolkit.py` | Same |
| `h_arcane/benchmarks/researchrubrics/toolkit.py` | Same |
| `h_arcane/benchmarks/gdpeval/factories.py` | Add `task_id` to `create_toolkit()` signature |
| `h_arcane/benchmarks/registry.py` | Update factory signatures to include `task_id` |
| `h_arcane/core/_internal/infrastructure/sandbox.py` | Change key from `run_id` to `task_id` |
| `h_arcane/core/_internal/task/inngest_functions/worker_execute.py` | Configure worker, build SDK context, persist actions from result |
| `h_arcane/core/_internal/task/conversions.py` | New: `db_resource_to_sdk()`, etc. |

### Test Changes

```python
# tests/e2e/test_gdpeval_e2e.py - after migration

async def test_gdpeval_single_task():
    """Test running a single GDPEval task."""
    # Before: user creates worker manually
    # worker = ReActWorker(model="gpt-4o", config=GDPEVAL_CONFIG)
    # task = load_gdpeval_task("task_001", worker)
    
    # After: loader handles worker creation
    task = load_gdpeval_task("task_001", model="gpt-4o")
    
    result = await execute_task(task, timeout_seconds=300)
    
    assert result.success
    assert result.score is not None
```

---

## Benefits

1. **Single Source of Truth**: SDK types are the contract, internal types are implementation details
2. **User-Friendly**: Users implement one protocol (`BaseWorker`) that actually works
3. **Type Safety**: No more lying type hints
4. **Extensibility**: New workers (DummyWorker, custom workers) follow the same pattern
5. **Testability**: Can test workers with mock `WorkerContext` without full infrastructure

---

## Complete File Change Summary

### Core SDK (Source of Truth - Mostly Unchanged)

| File | Status | Notes |
|------|--------|-------|
| `h_arcane/core/task.py` | ✅ Keep | Task, Resource, TaskStatus |
| `h_arcane/core/worker.py` | ✅ Keep | BaseWorker, WorkerContext, WorkerResult |
| `h_arcane/core/runner.py` | ✅ Keep | execute_task, ExecutionResult |
| `h_arcane/__init__.py` | ✅ Keep | Public exports |

### Execution Layer (Needs Updates)

| File | Status | Change |
|------|--------|--------|
| `h_arcane/core/_internal/task/inngest_functions/worker_execute.py` | 🔄 Update | Configure worker, build SDK context (sandbox by task_id), persist trace data from result |
| `h_arcane/core/_internal/task/conversions.py` | ➕ New | `db_resource_to_sdk()`, `sdk_resource_to_db()` |
| `h_arcane/core/_internal/task/persistence.py` | 🔄 Update | Use conversion utilities |
| `h_arcane/core/_internal/task/worker_context.py` | ✅ Keep | Still stores SDK workers |
| `h_arcane/core/_internal/infrastructure/sandbox.py` | 🔄 Update | Change key from `run_id` to `task_id` |

### Internal Types (Cleanup)

| File | Status | Change |
|------|--------|--------|
| `h_arcane/core/_internal/agents/base.py` | 🔄 Update | Remove duplicate `BaseWorker`, keep `BaseToolkit`, `BaseStakeholder` |
| `h_arcane/core/_internal/agents/base.py` | 🔄 Update | Rename `WorkerExecutionOutput` → `AgentOutput` or remove |

### Benchmark Workers

| File | Status | Change |
|------|--------|--------|
| `h_arcane/benchmarks/common/workers/react_worker.py` | 🔄 Major Update | Add `configure_for_execution()`, return trace data in `WorkerResult` |
| `h_arcane/benchmarks/common/workers/config.py` | ✅ Keep | WorkerConfig still useful |
| `h_arcane/benchmarks/common/workers/tracing.py` | 🔄 Update | Move persistence to execution layer, add dashboard events |

### Benchmark Loaders

| File | Status | Change |
|------|--------|--------|
| `h_arcane/benchmarks/gdpeval/loader.py` | 🔄 Update | Simplify API, optionally create worker internally |
| `h_arcane/benchmarks/minif2f/loader.py` | 🔄 Update | Same |
| `h_arcane/benchmarks/researchrubrics/loader.py` | 🔄 Update | Same |

### Benchmark Toolkits/Factories (Need Updates)

| File | Status | Change |
|------|--------|--------|
| `h_arcane/benchmarks/gdpeval/toolkit.py` | 🔄 Update | Add `task_id`, change `run_skill(run_id,...)` → `run_skill(task_id,...)`, add `get_qa_history()` |
| `h_arcane/benchmarks/minif2f/toolkit.py` | 🔄 Update | Same |
| `h_arcane/benchmarks/researchrubrics/toolkit.py` | 🔄 Update | Same |
| `h_arcane/benchmarks/gdpeval/factories.py` | 🔄 Update | Add `task_id` to `create_toolkit()` signature |
| `h_arcane/benchmarks/minif2f/factories.py` | 🔄 Update | Same |
| `h_arcane/benchmarks/researchrubrics/factories.py` | 🔄 Update | Same |
| `h_arcane/benchmarks/registry.py` | 🔄 Update | Update factory signatures to include `task_id` |
| `h_arcane/benchmarks/common/workers/tracing.py` | 🔄 Update | Split `log_actions_from_result()` → `extract_actions_from_result()` |

### Benchmark Stakeholders (Keep)

| File | Status | Notes |
|------|--------|-------|
| `h_arcane/benchmarks/gdpeval/stakeholder.py` | ✅ Keep | `RubricStakeholder` unchanged |
| `h_arcane/benchmarks/minif2f/stakeholder.py` | ✅ Keep | Unchanged |
| `h_arcane/benchmarks/researchrubrics/stakeholder.py` | ✅ Keep | Unchanged |

### Tests

| File | Status | Change |
|------|--------|--------|
| `tests/e2e/test_gdpeval_e2e.py` | 🔄 Update | Update to new loader API |
| `tests/e2e/test_minif2f_e2e.py` | 🔄 Update | Same |
| `tests/e2e/test_researchrubrics_e2e.py` | 🔄 Update | Same |
| `tests/unit/test_worker.py` | ➕ New | Test SDK worker protocol |

### Dashboard (New - Separate Concern)

| File | Status | Notes |
|------|--------|-------|
| `h_arcane/dashboard/__init__.py` | ➕ New | Dashboard event emission |
| `h_arcane/dashboard/events.py` | ✅ Exists | Event contracts already defined |
| `h_arcane/dashboard/emitter.py` | ➕ New | `DashboardEmitter` class |

**Dashboard event emission points (all in execution layer, NOT in worker):**

| Event | Emit Location | When |
|-------|---------------|------|
| `DashboardWorkflowStartedEvent` | `runner.py` or `workflow_start.py` | After run/experiment created |
| `DashboardTaskStatusChangedEvent` | `task_execute.py`, `task_propagate.py` | On task state transitions |
| `DashboardAgentActionCompletedEvent` | `worker_execute.py` | After action persisted to DB |
| `DashboardResourcePublishedEvent` | `persist_outputs.py` | After resource created |
| `DashboardWorkflowCompletedEvent` | `workflow_complete.py` | After final score calculated |

---

## Implementation Order

1. **Add conversion utilities** (`conversions.py`) - no breaking changes
2. **Update `BaseSandboxManager`** - change key from `run_id` to `task_id`
3. **Update toolkit factories** - add `task_id` parameter
4. **Update toolkits** - add `task_id`, change `run_skill(run_id)` → `run_skill(task_id)`, add `get_qa_history()`
5. **Refactor `tracing.py`** - split `log_actions_from_result()` → `extract_actions_from_result()` (returns actions without persisting)
6. **Update `ReActWorker`** - add `configure_for_execution()`, return trace data in `WorkerResult`
7. **Update `worker_execute_fn`** - configure worker, build SDK context, extract actions and persist with run_id
8. **Update benchmark loaders** - simplify API
9. **Add dashboard event emission** - emit after action persistence
10. **Clean up internal types** - remove duplicates
11. **Update tests** - verify all benchmarks pass
12. **Update documentation** - reflect SDK-first design
