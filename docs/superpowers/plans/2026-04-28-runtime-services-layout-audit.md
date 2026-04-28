# Runtime Services Layout Audit

Date: 2026-04-28

Scope: `ergon_core/ergon_core/core/runtime/services` in the `core-schema-dedup` worktree.

This note is an investigation artifact for a later fix/refactor plan. It does not propose a final migration sequence yet. The goal is to identify where `runtime/services` has become a dumping ground, where service shapes are inconsistent, and where logic appears duplicated or split across weak domain boundaries.

## Executive Summary

`runtime/services` is doing too many jobs in one flat namespace:

- Domain orchestration services (`TaskExecutionService`, `WorkflowInitializationService`, `WorkflowFinalizationService`).
- Graph mutation and graph read helpers (`WorkflowGraphRepository`, `GraphNodeLookup`, graph DTOs).
- Agent/tool-facing subtask services (`TaskManagementService`, `TaskInspectionService`).
- API/dashboard read models (`RunReadService`, `WorkflowService`).
- Persistence helpers (`ExperimentPersistenceService`, `EvaluationPersistenceService`).
- Product areas that are not obviously part of runtime orchestration (`CommunicationService`, cohort services).
- Transport contracts for Inngest and API surfaces (`*_dto.py`, `*_schemas.py`, `child_function_payloads.py`, `inngest_function_results.py`).

The resulting issue is not just file count. The same concepts are implemented with different local conventions: request/response models may be named DTOs, schemas, payloads, or function results; DB access may use explicit sessions, `with get_session()`, or ad hoc repository instances; graph traversal and latest-execution lookup logic are repeated with inconsistent ordering rules.

## Current File Groups

### Graph And Graph Mutation

- `graph_repository.py`
- `graph_lookup.py`
- `graph_dto.py`
- `task_management_service.py`
- `task_inspection_service.py`
- `task_management_dto.py`
- `task_inspection_dto.py`
- `subtask_cancellation_service.py`
- `subtask_cancellation_dto.py`
- `subtask_blocking_service.py`

This is the densest cluster. It covers graph mutation, graph traversal, task/subtask management, inspection, cancellation, blocking, and graph DTOs.

### Workflow And Run Lifecycle

- `run_service.py`
- `workflow_initialization_service.py`
- `workflow_finalization_service.py`
- `workflow_service.py`
- `workflow_dto.py`
- `orchestration_dto.py`

This group mixes run lifecycle orchestration with workflow navigation/resource materialization. `workflow_service.py` is read-heavy and tool/API-facing, while `workflow_initialization_service.py` and `workflow_finalization_service.py` are engine lifecycle services.

### Task Execution And Propagation

- `task_execution_service.py`
- `task_propagation_service.py`
- `task_cleanup_service.py`
- `task_cleanup_dto.py`

This group owns execution row creation/finalization, graph status updates for task execution, propagation after completion/failure, and cleanup of cancelled task executions.

### Evaluation

- `rubric_evaluation_service.py`
- `evaluator_dispatch_service.py`
- `evaluation_persistence_service.py`
- `evaluation_dto.py`

This group mixes evaluator preparation, rubric execution, persistence, and dashboard DTO shaping.

### API Read Models And Product Features

- `run_read_service.py`
- `communication_service.py`
- `communication_schemas.py`
- `cohort_service.py`
- `cohort_stats_service.py`
- `cohort_schemas.py`

These are valid application services, but they are not the same kind of service as runtime orchestration. Their presence in the same flat package makes ownership harder to read.

### Transport Contracts

- `child_function_payloads.py`
- `inngest_function_results.py`
- plus the various `*_dto.py` and `*_schemas.py` files

These are request/response contracts, not services. They currently sit beside service implementations without a consistent folder or naming convention.

## Standardization Gaps

### No Common Service Module Shape

The desired structure is roughly:

- request/response models
- DB schema types
- `repository.py` or service implementation
- `errors.py` for custom domain/service exceptions
- optional `utils.py`

The current structure is flat and inconsistent:

- Some service request/response models live in `*_dto.py`.
- Some live in `*_schemas.py`.
- Inngest request models live in `child_function_payloads.py`.
- Inngest outputs live in `inngest_function_results.py`.
- Some service-specific helper models live in the same service file.
- Persistence-facing repositories live partly in `core/persistence` and partly in `runtime/services`.
- Custom exceptions live mostly in broad runtime error modules, not beside the service/domain that raises them.

This makes it difficult to infer whether a file is a domain service, transport contract, read model, or persistence adapter.

### Error Types Are Not Domain-Local

Some custom errors already exist under `core/runtime/errors`, for example graph, delegation, and Inngest-specific error modules. That is better than raising generic `ValueError` everywhere, but it still leaves service packages without local ownership of their failure modes.

The target convention should be: each runtime domain package owns an `errors.py` file for exceptions that are part of that domain contract. For example:

- `runtime/graph/errors.py` for graph structural and mutation errors.
- `runtime/tasks/errors.py` for task execution, task management, cleanup, cancellation, and inspection failures.
- `runtime/workflows/errors.py` for workflow initialization/finalization/lifecycle failures.
- `runtime/evaluation/errors.py` for evaluator dispatch, rubric evaluation, and evaluation persistence failures.
- `runtime/inngest/errors.py` for Inngest wrapper/contract/non-retryable errors.

This does not mean every exception class needs to move immediately. The refactor plan should move errors opportunistically with the package they belong to, and should prefer explicit custom exceptions over generic `ValueError`, `RuntimeError`, or assertion-style checks at service boundaries.

### Repository Naming Is Ambiguous

`WorkflowGraphRepository` is in `runtime/services/graph_repository.py`, while persistence repositories live in:

- `core/persistence/context/repository.py`
- `core/persistence/telemetry/repositories.py`

This is understandable because `WorkflowGraphRepository` owns runtime graph mutation semantics and audit-log writes, not just raw CRUD. Still, the package shape blurs whether repositories are persistence infrastructure or runtime domain services.

### Session Ownership Varies

Patterns include:

- Methods accepting an explicit `Session`.
- Services opening `with get_session() as session`.
- Services using `session = get_session()` with manual `finally: session.close()`.
- Repository classes receiving a session from callers.

Examples:

- `TaskManagementService`, `SubtaskCancellationService`, and `WorkflowService` accept caller-owned sessions.
- `RunReadService`, `RunService`, `WorkflowInitializationService`, and `WorkflowFinalizationService` open sessions internally.
- `EvaluationPersistenceService` manually opens and closes sessions instead of using `with get_session()`.

This makes transaction boundaries harder to reason about and complicates any future service package convention.

## Concrete Duplication Findings

### P1: Duplicate Latest Execution Lookup

Two files define the same helper:

- `task_management_service.py`
- `subtask_cancellation_service.py`

Both query `RunTaskExecution.id` by `node_id`, ordered by `RunTaskExecution.started_at.desc()`, and use it to populate `TaskCancelledEvent.execution_id`.

Related methods in other services define "latest execution" differently:

- `WorkflowService.get_latest_execution` orders by `attempt_number DESC`, then `started_at DESC`.
- `TaskInspectionService._latest_output` and `_latest_error` order only by `started_at DESC`.

This is a real semantic duplication. There should be one canonical helper for "latest execution for node", with a clearly documented ordering rule.

### P1: Duplicate Containment Subtree Traversal

The same parent-child BFS pattern appears in:

- `task_management_service.py` via `_count_non_terminal_descendants`.
- `subtask_cancellation_service.py` via `cancel_orphans`.
- `subtask_blocking_service.py` via `block_pending_descendants`.

All query `RunGraphNode` children by `run_id` and `parent_node_id`, then apply a different policy:

- Count non-terminal descendants.
- Cancel non-terminal descendants.
- Block non-terminal, non-running descendants.

This should become a shared graph traversal primitive, with the policy supplied by the caller or by domain-specific cascade services.

### P1: Scattered Graph Status Transitions

Graph node and edge status writes appear across:

- `task_execution_service.py`
- `task_propagation_service.py`
- `task_management_service.py`
- `subtask_cancellation_service.py`
- `subtask_blocking_service.py`
- `workflow_initialization_service.py`
- `graph_repository.py`

`WorkflowGraphRepository` intentionally does not validate transitions; it only records mutations and enforces structural invariants. That boundary is reasonable, but the transition policy above it is distributed across many services.

The refactor plan should decide whether there is a single graph lifecycle domain service, or at least a small set of named transition operations such as:

- start node execution
- complete node execution
- fail node execution
- reset node for restart
- cancel subtree
- block subtree
- satisfy dependency edge

### P2: Duplicated Graph Mapping / Read Loading

`GraphNodeLookup` batch-loads mappings from definition task IDs and edges to run graph IDs.

`RunReadService.build_run_snapshot` builds similar maps inline:

- `execution_task_map`
- `defn_to_node`
- task maps and context-event maps through API helper functions

`WorkflowService` also builds node maps through `_nodes_by_id` and tree/resource scopes through local queries.

These are not identical consumers, but the primitives overlap: load run graph, map definition IDs to node IDs, map executions to nodes, and traverse parent/child relationships.

### P2: Evaluation Score Semantics Drift

`WorkflowFinalizationService` computes:

- `final_score = sum(scores)`
- `normalized_score = final_score / len(scores)`

`RunReadService.build_run_snapshot` computes:

- `final_score = sum(scores) / len(scores)`

`TelemetryRepository.refresh_run_evaluation_summary` also updates summary fields from evaluation rows.

`cohort_service.py` and `cohort_stats_service.py` then read `normalized_score` and `final_score` from summary JSON. This should be centralized because downstream consumers depend on the meaning of these fields.

### P2: Read Model Shaping Depends On API Helpers

`RunReadService` imports DTOs from `ergon_core.core.api.schemas` and imports `ergon_core.core.api.runs` helper functions inside `build_run_snapshot`.

That means a runtime service depends upward on API helpers. This is likely a layering smell. The pure DTO helper functions should either move into a runtime/read-model package, or the API should own the service and not call it "runtime".

### P3: Repeated Graph Repository Construction

`WorkflowGraphRepository()` is constructed in many places:

- `task_execution_service.py`
- `task_propagation_service.py`
- `workflow_initialization_service.py`
- `task_management_service.py`
- `subtask_cancellation_service.py`
- `subtask_blocking_service.py`

The repository is mostly stateless, but it has mutation listeners. `TaskManagementService` registers `dashboard_emitter.graph_mutation`; other construction sites do not. If listeners are meant to be consistently applied, construction should be standardized. If not, the listener behavior should be explicit at call sites or separated from repository construction.

### P3: DTO Naming And Boundaries Are Mixed

Current naming patterns include:

- `graph_dto.py`
- `workflow_dto.py`
- `task_management_dto.py`
- `task_inspection_dto.py`
- `evaluation_dto.py`
- `cohort_schemas.py`
- `communication_schemas.py`
- `child_function_payloads.py`
- `inngest_function_results.py`

The differences may have history, but they do not communicate ownership. A student/user reading the package cannot easily tell whether "schema", "DTO", "payload", and "result" are meaningful distinctions.

### P3: Task Reference Shapes Overlap

The following are related but split:

- `GraphTaskRef` in `graph_dto.py`
- `TaskDescriptor` in `orchestration_dto.py`
- `SubtaskInfo` in `task_inspection_dto.py`
- `WorkflowDependencyRef.source` / `target` in `workflow_dto.py`
- `AddSubtaskResult`, `CancelTaskResult`, and `RestartTaskResult` in `task_management_dto.py`

Some separation is legitimate, but the shared task identity payload should be explicit. The current split risks reintroducing separate names/status fields for the same runtime graph node.

## Boundary Assessment

### Things That Belong Near Persistence

These are schema or data-access concerns:

- SQLModel table definitions in `core/persistence`.
- Shared DB session creation in `core/persistence/shared/db.py`.
- Shared persisted enums and types in `core/persistence/shared`.
- Context and telemetry repositories that are mostly append/read/write around specific persisted rows.
- Definition persistence may be a better fit near `core/persistence/definitions` than under `runtime/services`.

Candidate to move or reframe:

- `experiment_persistence_service.py`

It writes immutable experiment definition tables. It is not obviously a runtime orchestration service.

### Things That Belong In Runtime Domain Packages

These are runtime domain behavior, not raw persistence:

- Graph mutation repository and mutation DTOs.
- Task execution lifecycle.
- Propagation and graph lifecycle transitions.
- Agent/tool-facing task management and inspection.
- Inngest command/result contracts.

Candidate runtime packages:

- `runtime/graph`
- `runtime/tasks`
- `runtime/workflows`
- `runtime/evaluation`
- `runtime/read_models`
- `runtime/inngest/contracts`

The exact package names can wait for the refactor plan, but the target should be domain packages rather than one `services` bucket.

### Things Inngest Should Own

The Inngest function implementations already live under `core/runtime/inngest`, but two Inngest-owned modules currently sit at the top of `core/runtime`:

- `inngest_client.py`
- `inngest_registry.py`

These should move under `runtime/inngest` with the function modules. The Inngest package should own:

- the client singleton and shared cancellation configuration
- the function registry / function list passed to `serve()`
- function modules
- child-function request contracts and function result contracts, unless those contracts are better colocated with the specific function module
- Inngest-specific errors

This would make `runtime/inngest` the runtime boundary for event orchestration instead of spreading its setup across `runtime` and `runtime/services`.

### Things That Are Product/Application Services

These may belong outside the runtime kernel, or in separate runtime subdomains:

- `communication_service.py`
- `cohort_service.py`
- `cohort_stats_service.py`
- `run_read_service.py`

They are valid application concerns, but colocating them with graph mutation and task execution weakens the meaning of `services`.

## Suggested Target Shape

This is a sketch, not a final implementation plan.

```text
core/runtime/
  graph/
    models.py          # runtime DTOs for graph snapshots and mutation records
    repository.py      # WorkflowGraphRepository
    errors.py          # graph structural and mutation errors
    traversal.py       # subtree and dependency traversal primitives
    lookup.py          # GraphNodeLookup or successor
    lifecycle.py       # named graph status transitions, if introduced

  tasks/
    models.py          # task execution commands/results, task refs
    errors.py          # task execution/management/cancellation errors
    execution.py       # TaskExecutionService
    management.py      # agent-initiated subtask operations
    inspection.py      # read-only subtask snapshots
    cleanup.py         # per-execution cleanup
    cascades.py        # cancellation/blocking/downstream invalidation

  workflows/
    models.py          # workflow lifecycle commands/results
    errors.py
    initialization.py
    finalization.py
    service.py         # workflow navigation/resource materialization, if kept here

  evaluation/
    models.py
    errors.py
    dispatch.py
    rubric.py
    persistence.py
    scoring.py         # shared score aggregation semantics

  read_models/
    errors.py
    run_snapshot.py    # RunReadService and pure DTO shaping helpers

  inngest/
    client.py          # Inngest singleton and cancellation config
    registry.py        # ALL_FUNCTIONS / serve() function list
    contracts.py       # child payloads and function results, or per-event modules
    errors.py          # Inngest/non-retryable/contract wrapper errors
    functions/         # optional if we want one subdirectory below package root
```

The key convention is that each domain package should make its file roles obvious:

- `models.py` for request/response/domain DTOs.
- `repository.py` only where the module owns persisted mutation/read-write behavior.
- `errors.py` for exceptions that are part of that service/domain contract.
- `service.py` or named service files for use-case orchestration.
- `utils.py` or more specific helper modules only for reusable pure helpers.

For Inngest specifically, avoid a separate top-level `runtime/inngest_client.py` or `runtime/inngest_registry.py`; the `runtime/inngest` package should own those pieces directly.

## High-Value Refactor Candidates

### 1. Extract Graph Traversal Primitives

Create a small module for containment traversal by `parent_node_id`.

Initial consumers:

- `task_management_service._count_non_terminal_descendants`
- `subtask_cancellation_service.cancel_orphans`
- `subtask_blocking_service.block_pending_descendants`
- `workflow_service._descendant_ids`

This is the clearest low-risk cleanup because the duplicated query shape is visible and bounded.

### 2. Centralize Latest Execution Selection

Create one helper or repository method for "latest execution for node".

It should define ordering once, probably:

1. `attempt_number DESC`
2. `started_at DESC`

Then update:

- `WorkflowService.get_latest_execution`
- `TaskInspectionService._latest_output`
- `TaskInspectionService._latest_error`
- `task_management_service._latest_execution_id`
- `subtask_cancellation_service._latest_execution_id`

### 3. Centralize Evaluation Score Aggregation

Create one score aggregation helper that returns a named object:

- `final_score`
- `normalized_score`
- `evaluators_count`

Then update:

- `WorkflowFinalizationService`
- `TelemetryRepository.refresh_run_evaluation_summary`
- `RunReadService.build_run_snapshot`
- cohort summary readers if their semantics need adjustment

### 4. Split DTO/Schema Contracts From Service Implementations

Normalize naming inside any new package:

- Use `models.py` for request/response DTOs within runtime domain packages.
- Reserve `schemas.py` for API wire schemas only if the codebase keeps that distinction.
- Avoid mixing Inngest contracts with service DTOs unless the package name makes that explicit.

### 5. Move API Snapshot Helpers Out Of API Layer

`RunReadService` should not need to import `ergon_core.core.api.runs` helper functions. Move pure task/resource/evaluation snapshot builders to a runtime read-model module, or move `RunReadService` behind the API layer.

### 6. Decide Whether `WorkflowGraphRepository` Is A Repository Or Domain Service

Two defensible options:

- Keep it in runtime, but move it to `runtime/graph/repository.py` and make clear that it is a domain repository for graph mutations, not a generic persistence repository.
- Move it nearer `persistence/graph`, but prevent it from depending on runtime dashboard/event DTOs.

The first option probably fits the current design better because the repository writes audit mutations and encodes structural invariants, not just SQL CRUD.

### 7. Move Inngest Ownership Into The Inngest Package

Move or plan to move:

- `runtime/inngest_client.py` to `runtime/inngest/client.py`
- `runtime/inngest_registry.py` to `runtime/inngest/registry.py`
- `services/child_function_payloads.py` to `runtime/inngest/contracts.py` or per-function contract modules
- `services/inngest_function_results.py` to `runtime/inngest/contracts.py` or per-function result modules
- `runtime/errors/inngest_errors.py` to `runtime/inngest/errors.py`

This should be mostly import churn, but the plan should include architecture tests so Inngest setup does not drift back into `runtime/services`.

### 8. Add Domain-Local Error Modules

As packages are split, add `errors.py` to each domain package. The first pass can be mechanical:

- graph errors follow `WorkflowGraphRepository`
- delegation/task errors follow task management and inspection
- Inngest errors follow the Inngest client and functions
- evaluation-specific contract violations move with evaluation services if they are not broadly runtime-level

The plan should not require inventing custom errors for every possible branch in one pass. It should require that new service boundary failures use domain-specific exception types, and that moved services do not keep reaching into a shared dumping-ground error module when a local `errors.py` is clearer.

## Questions For The Refactor Plan

1. Should `services` disappear entirely in favor of domain packages, or should it remain as a compatibility import layer during migration?
2. Should request/response models live in `models.py` beside each domain package, or in separate `contracts.py` files when they are consumed by Inngest/API boundaries?
3. Should `WorkflowGraphRepository` emit/listen to dashboard mutations directly, or should dashboard emission sit above the repository?
4. Should read-model services be considered runtime services, API services, or their own `runtime/read_models` layer?
5. Should definition persistence move under `persistence/definitions`, or stay in runtime because it converts authored experiments into persisted definition rows?
6. Should each package expose its domain errors from `__init__.py`, or should callers import directly from `package.errors` to avoid new barrel behavior?
7. Should Inngest contracts be centralized in one `runtime/inngest/contracts.py`, or colocated with each function module?

## Recommended Next Step

Write a refactor plan that starts with mechanical, low-risk extractions before package moves:

1. Extract shared latest-execution helper.
2. Extract graph traversal helper.
3. Extract evaluation score aggregation helper.
4. Move pure run snapshot helper functions out of `core.api.runs`.
5. Move Inngest client, registry, contracts, results, and errors under `runtime/inngest`.
6. Introduce domain package structure with one package at a time, starting with `runtime/graph`.
7. Add `errors.py` to each package as services move, and replace generic service-boundary exceptions where the domain already has a clear failure type.
8. Move/rename services only after tests prove the helpers preserve behavior.

This order reduces risk because it fixes semantic duplication before large import churn.
