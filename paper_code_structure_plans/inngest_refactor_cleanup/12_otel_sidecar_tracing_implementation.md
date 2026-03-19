# OTEL Sidecar Tracing Implementation

This document turns the OTEL sidecar tracing idea into an implementation-ready spec for this codebase.

It follows the same architectural direction as the cleanup series:

- runners orchestrate
- services own business logic
- observability adapters stay infrastructure-owned
- Inngest remains the orchestration layer, not the tracing substrate

## Goal

Add end-to-end OTEL tracing for workflow execution so an engineer can inspect a full run in Jaeger through an OTEL collector sidecar.

The implementation should trace:

- workflow kickoff and workflow completion/failure
- task lifecycle and task execution attempts
- worker execution spans
- worker tool-call spans
- sandbox lifecycle and sandbox file operations
- sandbox `run_skill()` commands
- task evaluation and criterion evaluation

The implementation should not replace the existing dashboard event stream.

The OTEL tracer is a second, parallel observability stream.

## Decisions Locked For This Plan

These decisions were explicitly chosen for this plan:

- write the spec in `paper_code_structure_plans/`
- include sandbox file-operation spans in v1
- include service-layer `TraceSink` injection in this implementation wave

## Current Problem

Today the codebase has rich dashboard observability, but it does not produce structured OTEL traces.

The existing dashboard path:

- emits lifecycle and action events through Inngest
- is designed for live UI updates
- does not create span hierarchy
- does not expose traces to OTEL-native backends like Jaeger or Tempo

The code also has one important implementation wrinkle:

- workflow, task, worker, and evaluation logic execute in separate Inngest function invocations

That means we cannot model the root workflow span as one live in-memory span that opens in `workflow_start.py` and closes later in `workflow_complete.py`.

For this codebase, the OTEL implementation must be based on:

- deterministic trace identity from `run_id`
- deterministic span identity from workflow/task/execution/evaluation keys
- explicit start and end timestamps when exporting completed spans

## Target Outcome

After this work, a single workflow run should appear in Jaeger as one trace with a stable trace ID derived from `run_id`.

The target hierarchy is:

- `workflow.execute`
- `workflow.start`
- `task.execute`
- `sandbox.setup`
- `sandbox.file_ops`
- `worker.execute`
- `tool.<name>`
- `sandbox.run_skill`
- `persist.outputs`
- `evaluation.task`
- `evaluation.criterion`
- `workflow.complete` or `workflow.failed`

The dashboard emitter should continue to operate unchanged from the user's point of view.

## Key Design Rule

Do not try to keep cross-function OTEL spans open across separate Inngest invocations.

Instead:

- derive the same trace ID everywhere from `run_id`
- derive stable parent/child span IDs from semantic keys
- emit completed spans with explicit timestamps

This lets each orchestration boundary participate in one shared trace without runtime span context propagation.

## Architecture

### Trace identity

Use one trace ID per run:

- `trace_id = derive_trace_id(run_id)`

Use deterministic span IDs for well-known boundaries:

- workflow root span from `run_id`
- task span from `(run_id, task_id, attempt_number)`
- worker span from `(run_id, task_id, execution_id, "worker")`
- sandbox setup span from `(run_id, task_id, execution_id, "sandbox_setup")`
- sandbox file-op span from `(run_id, task_id, execution_id, operation_name, ordinal)`
- evaluation task span from `(run_id, task_id, evaluator_id)`
- evaluation criterion span from `(run_id, task_id, evaluator_id, stage_idx, criterion_idx)`

Tool-call spans do not need to be guessed from unstable runtime order.

Use the already-persisted `Action.id` as the basis for deterministic tool span IDs:

- tool span from `(run_id, action.id)`

### Span timing

Use persisted timestamps wherever possible:

- workflow root timing from `Run.started_at` and `Run.completed_at`
- task timing from `TaskExecution.started_at` and `TaskExecution.completed_at`
- tool timing from `Action.started_at` and `Action.completed_at`

Use local timing where the code currently does not persist timing:

- workflow-start orchestration step timing
- evaluation task timing
- evaluation criterion timing
- sandbox file-op timing
- sandbox setup timing if exact persisted timing is not already available

### Export path

The path is:

- app code -> OTEL SDK -> OTLP exporter -> `otel-collector` sidecar -> Jaeger

The app should not talk directly to Jaeger.

The collector owns fanout and backend-specific configuration.

### Tracing ownership

#### Infrastructure owns

- OTEL SDK bootstrap
- OTLP exporter configuration
- ID derivation helpers
- attribute serialization and truncation
- the concrete `OtelTraceSink`
- the no-op implementation

#### Runners own

- opening and closing orchestration boundary spans
- passing trace context into services
- emitting orchestration-side follow-up spans

#### Services own

- semantic events and sub-span creation through `TraceSink`
- adding structured events on important state transitions
- staying framework-agnostic with respect to Inngest

## Files

### New files

- `h_arcane/core/_internal/infrastructure/tracing.py`
- `config/otel-collector.yaml`

### Primary files to update

- `h_arcane/core/settings.py`
- `pyproject.toml`
- `docker-compose.yml`
- `h_arcane/core/runner.py`
- `h_arcane/core/worker.py`
- `h_arcane/core/_internal/task/inngest_functions/workflow_start.py`
- `h_arcane/core/_internal/task/inngest_functions/task_execute.py`
- `h_arcane/core/_internal/task/inngest_functions/sandbox_setup.py`
- `h_arcane/core/_internal/task/inngest_functions/worker_execute.py`
- `h_arcane/core/_internal/task/inngest_functions/persist_outputs.py`
- `h_arcane/core/_internal/task/inngest_functions/workflow_complete.py`
- `h_arcane/core/_internal/task/inngest_functions/workflow_failed.py`
- `h_arcane/core/_internal/evaluation/events.py`
- `h_arcane/core/_internal/evaluation/inngest_functions/check_evaluators.py`
- `h_arcane/core/_internal/evaluation/inngest_functions/task_run.py`
- `h_arcane/core/_internal/evaluation/inngest_functions/criterion.py`
- `h_arcane/core/_internal/infrastructure/sandbox.py`
- `h_arcane/core/_internal/task/services/dto.py`
- `h_arcane/core/_internal/task/services/task_execution_service.py`
- `h_arcane/core/_internal/task/services/workflow_initialization_service.py`
- `h_arcane/core/_internal/task/services/task_propagation_service.py`
- `h_arcane/core/_internal/task/services/workflow_finalization_service.py`
- `h_arcane/core/_internal/evaluation/services/*` as needed for optional service-level trace hooks

### Likely test files to add

- `tests/unit/test_tracing.py`
- `tests/unit/test_trace_sink_integration.py`
- targeted runner/service tests under `tests/unit/`

## New Dependencies

Add to `pyproject.toml`:

- `opentelemetry-sdk`
- `opentelemetry-api`
- `opentelemetry-exporter-otlp-proto-grpc`

Optional if needed for explicit resource helpers:

- `opentelemetry-semantic-conventions`

Use current latest compatible versions through the project package manager rather than hard-coding stale versions into the plan.

## Settings To Add

Add OTEL settings to `h_arcane/core/settings.py`.

Do not default any new string settings to `""`, because the settings module currently raises on empty string values.

Use safe defaults instead.

Suggested settings:

- `otel_traces_enabled: bool = False`
- `otel_service_name: str = "h-arcane"`
- `otel_exporter_otlp_endpoint: str = "http://localhost:4317"`
- `otel_exporter_otlp_insecure: bool = True`
- `otel_max_attribute_length: int = 4000`
- `otel_stdout_stderr_max_length: int = 4000`
- `otel_tool_payload_max_length: int = 4000`

## Infrastructure Contract

Create `h_arcane/core/_internal/infrastructure/tracing.py`.

It should contain the following pieces.

### `TraceContext`

Purpose:

- immutable tracing identity passed around by runners and services

Fields:

- `trace_id`
- `span_id`
- `parent_span_id`
- `run_id`
- `task_id`
- `execution_id`
- `evaluator_id`
- `attributes`

Not every field needs to be populated at every layer.

### `CompletedSpan`

Purpose:

- DTO for emitting a fully-formed span with explicit timestamps

Fields:

- `name`
- `trace_id`
- `span_id`
- `parent_span_id`
- `start_time`
- `end_time`
- `attributes`
- `status_code`
- `status_message`
- `events`

### `SpanEvent`

Purpose:

- structured event attached to a span

Fields:

- `name`
- `timestamp`
- `attributes`

### `TraceSink`

Purpose:

- framework-agnostic tracing interface used by services and orchestration helpers

Methods:

- `emit_span(span: CompletedSpan) -> None`
- `emit_event(trace_id: int, span_id: int, event: SpanEvent) -> None`
- `child_context(parent: TraceContext, *, name: str, span_key: str, attributes: dict | None = None) -> TraceContext`

Do not use an interface that assumes a live span object must stay open across process boundaries.

The sink contract for this codebase should be built around completed spans plus deterministic IDs.

### `OtelTraceSink`

Purpose:

- concrete OTEL implementation

Responsibilities:

- initialize tracer provider lazily
- configure OTLP exporter only when tracing is enabled
- emit spans with explicit start and end times
- map `CompletedSpan` into OTEL SDK spans
- serialize and truncate attributes safely

### `NoopTraceSink`

Purpose:

- default implementation when tracing is disabled or not configured

### Helper functions

Add helpers for:

- `trace_id_from_run_id(run_id: UUID) -> int`
- `span_id_from_key(*parts: str) -> int`
- `workflow_root_context(run_id: UUID) -> TraceContext`
- `task_context(run_id: UUID, task_id: UUID, attempt_number: int) -> TraceContext`
- `worker_context(run_id: UUID, task_id: UUID, execution_id: UUID) -> TraceContext`
- `evaluation_task_context(run_id: UUID, task_id: UUID, evaluator_id: UUID) -> TraceContext`
- `criterion_context(...) -> TraceContext`
- `safe_json_attribute(value: Any, max_length: int) -> str`
- `truncate_text(value: str | None, max_length: int) -> str | None`

## Required Refactor Before Instrumentation

There is currently duplicate sandbox setup behavior across the task path.

Today:

- `task_execute.py` invokes `sandbox_setup_fn`
- `worker_execute.py` still contains `_setup_sandbox(...)` and calls sandbox creation/upload again

This must be resolved before tracing is added.

Required outcome:

- `sandbox_setup.py` becomes the single place that creates the sandbox and uploads task inputs
- `worker_execute.py` consumes the already-created sandbox only

Reason:

- duplicate setup would create duplicate sandbox spans
- duplicate setup is also a functional correctness risk independent of tracing

## DTO And Event Changes

### `WorkerContext`

Update `h_arcane/core/worker.py`.

Add:

- `trace_context: TraceContext | None = None`
- `trace_sink: Any | None = None`

This gives worker-facing execution code access to tracing without introducing Inngest types.

### Evaluation events

Update `h_arcane/core/_internal/evaluation/events.py`.

`TaskEvaluationEvent` should gain:

- `task_id`
- `execution_id`
- `evaluator_id`
- optionally `experiment_id` if useful for attributes and debugging

`CriterionEvaluationEvent` should gain:

- `task_id`
- `execution_id`
- `evaluator_id`

Reason:

- evaluation spans need deterministic parent-child identity
- the current event payloads do not carry enough information to parent criterion spans under a specific task/evaluator path cleanly

### Task service DTOs

Update `h_arcane/core/_internal/task/services/dto.py`.

Add lightweight trace-aware fields where the service boundary benefits from them.

Prefer one of these patterns:

- pass `trace_context` and `trace_sink` directly into service constructors
- or pass a small `TraceDependencies` DTO into service methods

Recommendation:

- inject `trace_sink` into the service constructor
- pass `trace_context` in the command DTO when a specific call needs a parent context

This keeps the services framework-agnostic while still trace-aware.

## Service-Level Tracing Plan

This plan includes service-level tracing now, but the services should not become OTEL-specific.

### `TaskExecutionService`

Add optional tracing support for:

- preparation start/end
- execution finalization success/failure
- status transition events

Use:

- span events for state transitions
- child spans only where the operation is meaningful as a timed business step

### `WorkflowInitializationService`

Add optional tracing support for:

- workflow initialization phase
- initial task-state creation
- evaluator binding creation
- ready-task computation

### `TaskPropagationService`

Add optional tracing support for:

- propagation after task completion
- ready-task determination
- workflow terminal-state classification

### `WorkflowFinalizationService`

Add optional tracing support for:

- score aggregation
- execution result synthesis
- total-cost computation

Service tracing should enrich the task/workflow spans rather than explode the trace with low-value micro-spans.

Default rule:

- prefer span events first
- add child spans only for meaningful units with real duration and debugging value

## Runner Implementation Plan

## Phase 1: tracing bootstrap and configuration

### `settings.py`

Add the OTEL settings listed above.

### `tracing.py`

Implement:

- `TraceContext`
- `CompletedSpan`
- `SpanEvent`
- `TraceSink`
- `OtelTraceSink`
- `NoopTraceSink`
- deterministic ID helpers

### `runner.py`

At workflow kickoff:

- create or fetch the application trace sink
- derive the workflow root trace context from `run.id`
- record workflow kickoff metadata needed later for attributes

Do not attempt to keep a live root span open in `execute_task()`.

The root span will be synthesized later from persisted run timestamps.

The runner may still emit a short kickoff span or event if useful.

## Phase 2: fix sandbox setup ownership

### `sandbox_setup.py`

Make this the single owner of:

- sandbox creation
- initial directory setup
- input upload
- output directory prep

Emit:

- `sandbox.setup`
- optionally one grouped `sandbox.file_ops` span for initial input upload

### `worker_execute.py`

Remove:

- `_setup_sandbox(...)`
- the durable step that duplicates sandbox creation/upload

Keep:

- loading existing sandbox
- worker creation and worker execution

## Phase 3: workflow and task spans

### `workflow_start.py`

Emit a short `workflow.start` span with:

- `run_id`
- `experiment_id`
- `workflow_name`
- `total_tasks`
- `total_leaf_tasks`
- `dependency_count`
- `evaluator_count`

Add span events for:

- initial pending-state creation
- initial ready-task marking

This is not the root span.

It is the workflow-start orchestration span.

### `task_execute.py`

Emit `task.execute` using the current task execution attempt as identity.

Attributes:

- `run_id`
- `experiment_id`
- `task_id`
- `task_name`
- `parent_task_id`
- `execution_id`
- `attempt_number`
- `benchmark_name`

Add span events for:

- `status.pending`
- `status.ready`
- `status.running`
- `status.completed`
- `status.failed`

Use `TaskExecution.started_at` and `TaskExecution.completed_at` once available for the final emitted task span.

If the task runner needs to emit a provisional span before completion, keep it local and still export one final completed span using persisted timestamps.

### `workflow_complete.py`

Emit:

- `workflow.complete`
- the synthetic root `workflow.execute`

For `workflow.execute`, use:

- `Run.started_at` as start time
- `Run.completed_at` as end time

Attributes:

- `run_id`
- `experiment_id`
- `benchmark_name`
- `worker_model`
- `final_score`
- `normalized_score`
- `total_cost_usd`
- `success = true`

### `workflow_failed.py`

Emit:

- `workflow.failed`
- the synthetic root `workflow.execute` with failure status

Attributes:

- `run_id`
- `experiment_id`
- `error`
- `success = false`

## Phase 4: worker and tool-call spans

### `worker_execute.py`

Emit `worker.execute` around the worker call.

Attributes:

- `run_id`
- `task_id`
- `execution_id`
- `agent_config_id`
- `worker_name`
- `worker_model`
- `benchmark_name`

Timing:

- local timing around `await worker.execute(...)`

### Tool spans

After `worker.execute()` returns:

- iterate `result.actions`
- persist each `Action` if not already persisted
- emit one `tool.<action_type>` span per action

Use:

- `Action.id` as stable span identity input
- `Action.started_at` and `Action.completed_at` for timing

Attributes:

- `run_id`
- `task_id`
- `execution_id`
- `action_id`
- `action_num`
- `action_type`
- `success`
- `duration_ms`
- `agent_total_tokens`
- `agent_total_cost_usd`
- truncated `input`
- truncated `output`
- serialized `error`

This plan intentionally keeps tool tracing post-hoc for v1.

Do not add live tool hooks to `react_worker.py` in this phase.

## Phase 5: sandbox spans

### `sandbox.py`

Instrument these methods:

- `create(...)`
- `upload_inputs(...)`
- `upload_file(...)`
- `download_file(...)`
- `download_all_outputs(...)`
- `run_skill(...)`
- optionally `list_files(...)` if it proves useful

Span model:

- `sandbox.setup` for creation and environment preparation
- `sandbox.file_ops` for file movement operations
- `sandbox.run_skill` for skill execution

Suggested attributes for `sandbox.setup`:

- `run_id`
- `task_id`
- `sandbox_id`
- `timeout_minutes`
- `skills_package`

Suggested attributes for `sandbox.file_ops`:

- `run_id`
- `task_id`
- `sandbox_id`
- `operation`
- `file_count`
- `file_paths` only when the list is short
- `bytes_transferred` where known

Suggested attributes for `sandbox.run_skill`:

- `run_id`
- `task_id`
- `sandbox_id`
- `skill_name`
- `command_type = "run_skill"`
- `success`
- truncated `stdout`
- truncated `stderr`
- error summary

`run_skill()` currently uses `sandbox.run_code(...)` and reads result files afterward.

Instrument both:

- the code execution itself
- the result-file read as a file-op sub-operation or span event

## Phase 6: persist outputs

### `persist_outputs.py`

Emit `persist.outputs` with:

- `run_id`
- `task_id`
- `execution_id`
- `sandbox_id`
- `outputs_count`
- `output_resource_ids`

This span should parent under `task.execute`.

If output download timing is already captured in sandbox file-op spans, avoid duplicating too much detail here.

Keep this span focused on the persistence phase and its aggregate result.

## Phase 7: evaluation tracing

### `check_evaluators.py`

When building `TaskEvaluationEvent`, include:

- `task_id`
- `execution_id`
- `evaluator_id`

This is required for deterministic evaluation span IDs.

### `task_run.py`

Emit `evaluation.task`.

Attributes:

- `run_id`
- `task_id`
- `execution_id`
- `evaluator_id`
- `rubric_type`
- `stages_evaluated`
- `normalized_score`

Parent:

- the relevant `task.execute` span

Timing:

- local timing around `evaluation_service.evaluate(...)`

### `criterion.py`

Emit `evaluation.criterion`.

Attributes:

- `run_id`
- `task_id`
- `execution_id`
- `evaluator_id`
- `stage_name`
- `stage_idx`
- `criterion_idx`
- `criterion_type`
- `score`
- `max_score`
- truncated `feedback`
- `success`

Parent:

- `evaluation.task`

Timing:

- local timing around criterion evaluation

## Detailed Implementation Order

Implement in this order.

1. Add OTEL dependencies and settings.
2. Add `tracing.py` with deterministic IDs, DTOs, sink implementations, and helpers.
3. Fix duplicate sandbox setup so there is one sandbox-creation path.
4. Thread `trace_sink` and `trace_context` through runner and worker context.
5. Add workflow and task-level spans.
6. Add worker and post-hoc tool-call spans.
7. Add sandbox setup, file-op, and `run_skill` spans.
8. Extend evaluation event contracts with task/execution/evaluator identity.
9. Add evaluation task and criterion spans.
10. Add `workflow.execute` synthesis in `workflow_complete.py` and `workflow_failed.py`.
11. Add collector and Jaeger local-dev configuration.
12. Add tests and run one manual end-to-end validation.

## Attribute Rules

To keep the trace usable and safe:

- truncate tool input/output payloads
- truncate `stdout` and `stderr`
- do not attach large task-tree blobs unless they are specifically useful
- prefer IDs and counts over raw large JSON
- serialize dict-like payloads to compact JSON strings before attaching

Suggested included workflow attributes:

- `run_id`
- `experiment_id`
- `benchmark_name`
- `worker_model`
- `task_count`
- `leaf_task_count`

Suggested excluded or heavily truncated attributes:

- full task tree JSON
- full tool outputs
- full sandbox stdout/stderr
- large evaluation prompts

## Docker Compose Shape

Update `docker-compose.yml` to add:

- `otel-collector`
- `jaeger`

Set app environment:

- `OTEL_TRACES_ENABLED=true`
- `OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317`
- `OTEL_SERVICE_NAME=h-arcane`

Collector should:

- receive OTLP over gRPC
- export to Jaeger

Jaeger should:

- enable OTLP ingestion
- expose the UI on a host port for local review

## Test Plan

Add tests for the following.

### Unit tests for tracing helpers

- same `run_id` always produces same `trace_id`
- same semantic key always produces same `span_id`
- different semantic keys produce different `span_id`s
- truncation helpers cap oversized payloads deterministically

### Unit tests for sink behavior

- `NoopTraceSink` accepts calls without side effects
- disabled tracing path returns no-op sink
- OTEL sink maps attributes and timestamps correctly

### Runner and service tests

- `task_execute.py` emits task span and final status event
- `worker_execute.py` emits worker span and tool spans from `Action`s
- `sandbox_setup.py` emits one sandbox setup path only
- `workflow_complete.py` emits synthetic root span with success attributes
- `workflow_failed.py` emits synthetic root span with failure attributes
- evaluation flow emits `evaluation.task` and child criterion spans

### Manual validation

Run one small local workflow and verify in Jaeger:

- exactly one trace per `run_id`
- `workflow.execute` is the root span
- `task.execute` spans are children of the workflow root
- `worker.execute` spans nest under tasks
- `tool.<name>` spans nest under `worker.execute`
- sandbox spans are present and attributed to the correct task
- evaluation spans parent correctly under the task path

## Acceptance Criteria

This work is done when:

- the app exports OTEL traces to the collector sidecar successfully
- a completed run appears in Jaeger as one trace keyed by `run_id`
- workflow, task, worker, tool, sandbox, output-persist, and evaluation spans are visible
- sandbox setup is no longer duplicated across `task_execute.py` and `worker_execute.py`
- services can emit trace events through `TraceSink` without importing Inngest or OTEL SDK types directly
- the dashboard emitter still works unchanged
- tracing can be disabled cleanly through config

## Non-Goals For This Phase

- real-time in-flight tool spans inside the worker loop
- replacing the dashboard event stream
- distributed context propagation through HTTP headers
- production sampling strategy redesign
- adding a cloud tracing vendor SDK

## Risks And Mitigations

### Risk: duplicated or conflicting sandbox spans

Mitigation:

- fix sandbox setup ownership before instrumentation

### Risk: trace volume becomes noisy

Mitigation:

- prefer aggregated file-op spans where needed
- truncate large payloads
- avoid low-value micro-spans

### Risk: evaluation spans cannot parent correctly

Mitigation:

- extend evaluation event payloads with `task_id`, `execution_id`, and `evaluator_id` before implementing evaluation tracing

### Risk: settings bootstrap breaks due to empty-string validation

Mitigation:

- use non-empty safe defaults for all OTEL string settings

## Engineer Notes

The most important implementation constraint in this codebase is this:

- OTEL context is not the source of truth

Persisted run/task/action data is the source of truth.

The tracing layer should reconstruct coherent spans from durable workflow data and explicit timestamps rather than assuming one long-lived in-process execution context.

That is the design choice that will make the resulting implementation stable across Inngest retries, separate function invocations, and post-hoc tool-call export.
