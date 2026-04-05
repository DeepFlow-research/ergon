# Typing & Code-Smell Audit: `arcane_extension_new`

---

## How this codebase differs from the old one

The new codebase already fixes the worst structural problem of the old one: **rubrics and criteria live behind ABCs in `h_arcane.api`** (`Evaluator`, `Rubric`, `Criterion`), not concrete benchmark types in core. There is no `AnyRubric`-style layering inversion. The public API types (`Worker`, `Evaluator`, `Criterion`, `BenchmarkTask`) are clean ABCs. That's a good starting point.

The issues that remain are different in character: **not** circular-import pressure, but rather **loose `dict[str, Any]` bags where typed models would be better**, some unnecessary `hasattr`/`getattr`, and an untyped worker context.

---

## Issues found

### 1. `Worker.execute()` context is `Mapping[str, Any] | None` — needs a typed `WorkerContext`

**File:** `h_arcane/h_arcane/api/worker.py`

```python
async def execute(
    self,
    task: BenchmarkTask,
    *,
    context: Mapping[str, Any] | None = None,
) -> WorkerResult:
```

This is the single weakest type in the public API. The `Mapping[str, Any]` bag is completely untyped, and today **no call site passes it** — the Inngest path calls `worker.execute(task)` with no context, making the parameter dead code. `ReActWorker` reads `tools` from the context bag, but that's a design smell: tools are a property of the worker, not the execution context.

#### Design: separate concerns

**Tools belong on the Worker.** The benchmark/orchestration layer should construct the worker with its tools at creation time:

```python
toolkit = GDPEvalToolkit(sandbox_manager=..., task_id=..., run_id=...)
worker = ReActWorker(name="worker", model="openai:gpt-4o", tools=toolkit.get_tools())
```

**WorkerContext is per-execution runtime state** — things the worker can't know until it's actually running a specific task. It should be lean:

```python
class WorkerContext(BaseModel):
    """Per-execution runtime state passed to Worker.execute()."""

    model_config = {"frozen": True}

    run_id: UUID
    task_id: UUID
    execution_id: UUID
    sandbox_id: str
    metadata: dict[str, Any] = Field(default_factory=dict)
```

Key design decisions:
- **`sandbox_id: str` (required, not nullable)** — the Inngest flow always runs `sandbox_setup_fn` before `worker_execute_fn`. By the time a worker runs, there's always a sandbox. Making this nullable would be lying about the contract.
- **No `tools`** — tools are a property of the worker, set at construction. Workers like `ReActWorker` should accept `tools` in `__init__`, not fish them out of a context bag.
- **No `toolkit`** — toolkits are benchmark-specific (`GDPEvalToolkit`, `MiniF2FToolkit`, etc.). The orchestration layer builds the toolkit, calls `.get_tools()`, and passes the result to the worker constructor. Workers don't know what benchmark they're running under.
- **No `trace_context` / `trace_sink`** — tracing is an infrastructure concern handled by the Inngest layer and the tracing module's global `get_trace_sink()`. Workers don't manage their own tracing.
- **No `sandbox` handle** — unlike the old codebase's `SandboxHandle` protocol, the new architecture manages sandboxes externally via `BaseSandboxManager`. Workers get the ID if they need it; actual sandbox interaction happens through toolkit tools.

#### Changes required

1. **Create `WorkerContext`** in `h_arcane/h_arcane/api/worker_context.py`
2. **Update `Worker.execute()` signature** — `context: Mapping[str, Any] | None = None` → `context: WorkerContext`
3. **Update `ReActWorker`** — accept `tools` in `__init__`, stop reading from context bag
4. **Update `StubWorker`** — accept `context: WorkerContext` in `execute()`
5. **Wire `worker_execute.py`** — construct `WorkerContext` from `WorkerExecuteRequest` fields and pass it
6. **Wire `execute_task_fn`** — ensure `sandbox_id` (from `SandboxReadyResult`) flows through to the worker
7. **Update tests** — construct `WorkerContext` in test call sites

---

### 2. Pervasive `dict[str, Any]` metadata bags

Almost every public model has an escape hatch:

| Model | Field | File |
|-------|-------|------|
| `BenchmarkTask` | `task_payload: dict[str, Any]` | `api/task_types.py` |
| `WorkerResult` | `artifacts: dict[str, Any]`, `metadata: dict[str, Any]` | `api/results.py` |
| `CriterionResult` | `metadata: dict[str, Any]` | `api/results.py` |
| `TaskEvaluationResult` | `metadata: dict[str, Any]` | `api/results.py` |
| `EvaluationContext` | `metadata: dict[str, Any]` | `api/evaluation_context.py` |
| `PersistedExperimentDefinition` | `metadata: dict[str, Any]` | `api/handles.py` |
| `ExperimentRunHandle` | `metadata: dict[str, Any]` | `api/handles.py` |
| `Worker.__init__` | `metadata: dict[str, Any]` | `api/worker.py` |
| `Evaluator.__init__` | `metadata: dict[str, Any]` | `api/evaluator.py` |
| `Criterion.__init__` | `metadata: dict[str, Any]` | `api/criterion.py` |

**Some of these are fine** — a generic metadata bag on `Worker` or `Experiment` is a reasonable extension point. But `task_payload`, `artifacts`, and `agent_outputs`-style fields should grow typed alternatives per benchmark. This is a backlog item, not a blocker.

**Recommendation:** Accept `metadata: dict[str, Any]` on the generic base types. For benchmark-specific data, use typed `BenchmarkTask` subclasses (which the design already supports — `model_config = {"frozen": True}` on a `BaseModel`). Flag `task_payload` as a candidate for typed subclass fields.

---

### 3. `hasattr` / `getattr` duck-typing

| File | Pattern |
|------|---------|
| `react_worker.py` | `getattr(message, "timestamp", ...)` |
| `minif2f/toolkit.py` | `getattr(cmd_err, "stdout"/"stderr"/"exit_code", ...)` — E2B exception attrs |
| `instrumentation.py` | `getattr` on command results, `__getattr__` delegation |
| `queries.py` | `getattr(entity, "id", None)` |
| `saved_specs/repositories.py` | `hasattr(row, "updated_at")` |
| `trace_check.py` | `getattr(result, "artifacts", {})` |
| `file_check.py` | `getattr(result, "output"/"artifacts", ...)` |
| `discovery/__init__.py` | `getattr(cls, "type_slug"/"__doc__", ...)` |
| `manager.py` | `hasattr(resource, "load_content")`, `hasattr(resource, "file_path")` |

**Recommendation:**
- `instrumentation.py` `__getattr__` delegation: **keep** (thin proxy pattern, intentional).
- `discovery/__init__.py` `getattr(cls, "type_slug")`: Fine — introspecting ABCs.
- `manager.py` `hasattr(resource, ...)`: Define a `ResourceLike` protocol with `load_content()` and `file_path` so consumers don't duck-type.
- `trace_check.py` / `file_check.py`: Use `WorkerResult` model fields directly (`.artifacts`) instead of `getattr`.
- `queries.py` `getattr(entity, "id")`: Use typed entity protocol or explicit attribute.
- `react_worker.py` `getattr(message, "timestamp")`: Use the typed `ModelMessage` `timestamp` attribute from pydantic-ai (it exists).
- `minif2f/toolkit.py`: E2B exception attrs are third-party; `getattr` is acceptable but document the expected shape.

---

### 4. `extra: "allow"` on event contracts

**Files:**
- `h_arcane/.../runtime/events/base.py` — `InngestEventContract` uses `extra="allow"`
- `h_arcane/.../runtime/events/evaluation_events.py` — `TaskEvaluationEvent`, `CriterionEvaluationEvent` repeat it
- `h_arcane/.../runtime/services/child_function_payloads.py` — `SandboxSetupRequest`, `WorkerExecuteRequest`, `PersistOutputsRequest`

**Assessment:** `extra="allow"` on `InngestEventContract` is **correct and necessary** — Inngest injects private metadata fields like `_inngest` into `ctx.event.data`, so the base model must accept unknown keys. The child payloads inherit this for the same reason. The evaluation events repeating it is redundant (they inherit from the base) but harmless.

**Recommendation:** Keep `extra="allow"` on `InngestEventContract`. Remove the redundant `model_config` overrides on evaluation events since they inherit the base config. No action needed on child payloads — they correctly inherit the base behavior.

---

### 5. `arbitrary_types_allowed` on evaluation schemas

**Files:**
- `evaluation_schemas.py`: `CriterionContext`, `TaskEvaluationContext`, `CriterionSpec`
- `gdpeval/rubric.py`: `EvaluationStage`

**Issue:** `CriterionSpec.criterion` holds a `Criterion` ABC instance. Pydantic needs `arbitrary_types_allowed` for that.

**Recommendation:** This is correct and necessary — ABC instances don't have Pydantic schemas. Keep it. Consider whether `CriterionSpec` should be a plain dataclass instead of a Pydantic model (it's an internal orchestration type, not serialized over the wire).

---

### 6. Function-scoped imports

**Legitimate (keep):**
- `tracing.py`: OpenTelemetry lazy imports — optional dependency
- `experiment.py` `.persist()` / `.run()`: service imports to break `api → runtime` cycles
- `benchmark_run_start.py`: Inngest function body imports
- `gdpeval/loader.py`: `pandas` inside `_load_parquet`
- `researchrubrics/benchmark.py`: `datasets`/`huggingface_hub`
- `criterion_runtime.py`: `AsyncOpenAI`, `settings`

**Consolidate / review:**
- `arcane_cli/commands/benchmark.py`: 6+ lazy imports inside the handler; consider a `_benchmark_deps()` helper or move to top-level since CLI commands run after full import.
- `arcane_cli/discovery/__init__.py`: imports `BENCHMARKS`, `WORKERS`, `EVALUATORS` per function — could be a single top-level import.

---

### 7. Inngest worker path doesn't pass context

**File:** `h_arcane/.../runtime/inngest/worker_execute.py`

The Inngest worker invocation calls `await worker.execute(task)` **without** a `context` kwarg. This means `react_worker`'s context-dependent code (reading toolkit, sandbox_id from context) is dead on the Inngest path.

This is resolved by Issue 1: once `WorkerContext` exists, `worker_execute.py` constructs it from `WorkerExecuteRequest` fields (`run_id`, `task_id`, `execution_id`, `sandbox_id`) and passes it.

---

### 8. Bare `dict` (unparameterized) in persistence and services

Several internal modules use `dict` without type parameters:

- `serialization.py`: `deserialize_rubric(..., config: dict)`
- `cohort_schemas.py`: `metadata: dict`
- `experiment_persistence_service.py`: `snapshot: dict`
- `gdpeval/task_schemas.py`: `rubric_data: dict`
- `emitter.py`: `summary_data: dict`
- Inngest handlers returning `-> dict`

**Recommendation:** Add `[str, Any]` at minimum for clarity. Better: define typed return models for Inngest function results (the old codebase had `WorkflowStartResult`, `WorkflowCompleteResult`, etc.).

---

## Suggested phases

| Phase | Scope | Impact |
|-------|-------|--------|
| **A** | Introduce `WorkerContext` model; update `Worker.execute()` signature; move tools to `ReActWorker.__init__`; wire through `worker_execute.py` Inngest path | Biggest single win — types the untyped context, enforces sandbox_id non-null, separates tool ownership from execution context |
| **B** | Remove redundant `extra="allow"` overrides on evaluation events (they inherit from base) | Trivial cleanup |
| **C** | Replace `hasattr`/`getattr` with protocols or direct field access where feasible | Cleaner control flow |
| **D** | Parameterize bare `dict` → `dict[str, Any]`; typed `BenchmarkTask` subclass pattern for benchmarks | Incremental clarity |
| **E** | Consolidate CLI lazy imports | Minor cleanup |

---

## What's already good (no action needed)

- **Evaluator/Criterion/Rubric** type hierarchy: clean ABCs, no layering inversion.
- **`BaseModel` with `frozen=True`** on all public result types: immutable by default.
- **Registry pattern** (`arcane_builtins/registry.py`): slug-based, no import-time cycles.
- **`TYPE_CHECKING` usage**: minimal and justified (sandbox manager forward refs).
- **`from __future__ import annotations`**: used consistently where needed.
- **Tracing**: `TraceSink` protocol + `NoopTraceSink` / `OtelTraceSink` + global `get_trace_sink()` is the right pattern — no need to thread it through workers.
- **Inngest function results**: already typed (`WorkerExecuteResult`, `SandboxReadyResult`, etc.) unlike the old codebase.
