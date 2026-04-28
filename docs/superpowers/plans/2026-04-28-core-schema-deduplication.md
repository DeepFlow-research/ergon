# Core Schema Deduplication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make core workflow statuses, evaluation statuses, graph mutation payloads, event causes, and projection schemas have one clear source of truth per domain.

**Architecture:** Keep persisted table schemas in `core/persistence/*`, graph lifecycle conventions in `core/persistence/graph/status_conventions.py`, typed graph mutation payloads in `core/runtime/services/graph_dto.py`, evaluation summary status in `core/persistence/telemetry/evaluation_summary.py`, and transport-specific projections in `core/api/schemas.py` and `core/dashboard/event_contracts.py`. REST and dashboard layers may project canonical DTOs, but must not redefine domain meaning.

**Tech Stack:** Python 3.13, Pydantic v2, SQLModel, pytest, ty-compatible type aliases, existing Ergon core runtime/persistence packages.

---

## Source Of Truth Decisions

| Concept | Source of truth | Consumers should import from | Cleanup rule |
|---|---|---|---|
| Run row lifecycle | `ergon_core.core.persistence.shared.enums.RunStatus` | `core.persistence.shared.enums` | Only use for `RunRecord.status` and run-level orchestration. |
| Task execution row lifecycle | `ergon_core.core.persistence.shared.enums.TaskExecutionStatus` | `core.persistence.shared.enums` | Only use for `RunTaskExecution.status`; do not use it as the graph-node status type. |
| Graph node lifecycle | `ergon_core.core.persistence.graph.status_conventions.NodeStatus` and constants | `core.persistence.graph.status_conventions` | Use for `RunGraphNode.status`, propagation, subtask inspection, dashboard task-node status, and graph DTO status annotations. |
| Graph edge lifecycle | `ergon_core.core.persistence.graph.status_conventions.EdgeStatus` and constants | `core.persistence.graph.status_conventions` | Use for `RunGraphEdge.status` and edge mutation/status changes. |
| Graph target and mutation names | `GraphTargetType`, `MutationType` in `core/persistence/graph/models.py` | `core.persistence.graph.models` | Keep because these are persisted mutation-log contract names. |
| Graph mutation payload body | `GraphMutationValue` union in `core/runtime/services/graph_dto.py` | `core.runtime.services.graph_dto` | REST and dashboard events import this union; no separate payload definitions. |
| Evaluation criterion status | `EvalCriterionStatus` in `core/persistence/telemetry/evaluation_summary.py` | `core.persistence.telemetry.evaluation_summary` | REST evaluation DTOs import this alias. |
| Cancel cause | `CancelCause` in `core/runtime/events/task_events.py` | `core.runtime.events.task_events` | Services that accept cancel causes import the shared alias or narrower named aliases from the same module. |
| Context event payloads | `ContextEventType`, `ContextEventPayload` in `core/persistence/context/event_payloads.py` | `core.persistence.context.event_payloads` | REST/dashboard context event snapshots should use the canonical type where practical. |
| Generation transcript parts | `core/generation.py` | `core.generation` | Keep separate from context event payloads; add adapter tests for the mapping instead of merging naming schemes. |

---

## DTO Collapse Targets

The cleanup should collapse duplicate DTOs when two classes carry the same domain payload with only superficial transport differences. Keep separate models only when the shape is genuinely different at the boundary.

| Current duplication | Collapse target | Keep separate? | Why |
|---|---|---|---|
| `GraphMutationDto`, `RunGraphMutationDto`, `DashboardGraphMutationEvent` repeat mutation identity/body fields | Add canonical `GraphMutationRecordDto` in `core/runtime/services/graph_dto.py`; REST returns it, dashboard event embeds it or is a thin envelope around it | Keep dashboard event envelope only | Mutation body and metadata are one concept; REST/dashboard differ only by transport envelope and timestamp naming. |
| `RunContextEventDto` and `DashboardContextEventEvent` repeat context-event fields, but REST is untyped | Add canonical `ContextEventDto` near `core/persistence/context/event_payloads.py` or `core/runtime/services/context_dto.py`; both REST and dashboard use `ContextEventType` + `ContextEventPayload` | Keep event envelope name only | Same persisted event snapshot should not have typed dashboard payload and untyped REST payload. |
| `WorkflowTaskRef` mostly duplicates a subset of `GraphNodeDto` | Prefer `GraphNodeDto` directly where the full node snapshot is acceptable; otherwise create one canonical `GraphTaskRef` in `graph_dto.py` and use it across workflow DTOs | Maybe | CLI/tool responses may intentionally omit fields, but the current separate class adds another status/name surface. |
| `RunTaskDto` and `TaskTreeNode` both represent UI task nodes but one is map-oriented and one is recursive | Extract a shared `TaskNodeSnapshot` payload if frontend compatibility allows; keep `RunSnapshotDto.tasks: dict[str, ...]` and `DashboardWorkflowStartedEvent.task_tree` as containers | Yes, containers differ | Map vs tree is a real transport difference; the task-node payload fields should not drift. |
| `TestGraphNodeDto` and `TestGraphMutationDto` are Playwright-only projections | Leave separate but derive from canonical DTO conversion helpers where possible | Yes | Test harness is intentionally narrow/additive-only, but should not define new domain semantics. |

Rule: collapse the payload, not necessarily the envelope. For example, `DashboardGraphMutationEvent` can remain an event contract, but it should carry the same canonical mutation record/payload as REST and repository code.

---

## File Structure

**Modify:**
- `ergon_core/ergon_core/core/persistence/graph/status_conventions.py` — canonical graph status aliases, terminal/settled helpers, and small predicates.
- `ergon_core/ergon_core/core/runtime/execution/propagation.py` — use graph status constants consistently and align failure docs/results with `BLOCKED` behavior.
- `ergon_core/ergon_core/core/runtime/services/task_propagation_service.py` — remove stale cancellation wording and stop exposing unused invalidated targets from normal propagation if tests confirm it is dead.
- `ergon_core/ergon_core/core/runtime/inngest/propagate_execution.py` — remove dead `TaskCancelledEvent` emission from propagation if `invalidated_targets` is removed.
- `ergon_core/ergon_core/core/runtime/services/orchestration_dto.py` — simplify `PropagationResult` around actual ready/block/terminal outcomes.
- `ergon_core/ergon_core/core/runtime/services/task_inspection_dto.py` — use `NodeStatus` directly instead of duplicating or aliasing `SubtaskStatus`.
- `ergon_core/ergon_core/core/persistence/telemetry/evaluation_summary.py` — keep `EvalCriterionStatus` canonical.
- `ergon_core/ergon_core/core/api/schemas.py` — import `EvalCriterionStatus`, remove duplicate mutation/context payload bodies, and keep REST projection thin.
- `ergon_core/ergon_core/core/runtime/services/graph_dto.py` — make `GraphMutationValue` the only typed mutation payload body and make edge mutation IDs consistent with graph DTO ID types.
- `ergon_core/ergon_core/core/dashboard/event_contracts.py` — keep event envelopes but reuse canonical graph mutation/context event DTO payloads.
- `ergon_core/ergon_core/core/runtime/events/task_events.py` — keep `CancelCause` canonical and add subset aliases if services need narrower inputs.
- `ergon_core/ergon_core/core/runtime/services/subtask_cancellation_service.py` — import shared cancel-cause aliases instead of duplicating string literals.
- `ergon_core/ergon_core/core/runtime/services/subtask_blocking_service.py` — share graph skip predicates from `status_conventions.py`.

**Add or modify tests:**
- `tests/unit/architecture/test_core_schema_sources.py` — architecture guard for duplicate literals and forbidden imports.
- `tests/unit/runtime/test_propagation_contracts.py` or existing propagation tests — assert failure propagation blocks downstream nodes and does not emit cancellation targets.
- `tests/unit/runtime/test_graph_mutation_contracts.py` or existing graph repository tests — assert REST/dashboard mutation payloads accept the same `GraphMutationValue` body.
- Existing focused tests: `tests/unit/runtime/test_workflow_service.py`, `tests/unit/runtime/test_dynamic_task_evaluation_mapping.py`, `tests/unit/dashboard/test_event_contract_types.py`, `tests/unit/architecture/test_model_field_descriptions.py`.

---

### Task 1: Guard Canonical Status Ownership

**Files:**
- Modify: `tests/unit/architecture/test_core_schema_sources.py`
- Modify: `ergon_core/ergon_core/core/persistence/graph/status_conventions.py`
- Modify: `ergon_core/ergon_core/core/runtime/services/task_inspection_dto.py`

- [ ] **Step 1: Write architecture tests that fail on duplicated graph status literals**

Create `tests/unit/architecture/test_core_schema_sources.py` with this first test:

```python
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_graph_status_literals_are_defined_only_in_status_conventions() -> None:
    offenders: list[str] = []
    duplicate_snippets = (
        'Literal["pending", "ready", "running", "completed", "failed", "cancelled", "blocked"]',
        'Literal["pending", "ready", "running", "completed", "failed", "blocked", "cancelled"]',
        'Literal["pending", "satisfied", "invalidated"]',
    )
    allowed = {
        ROOT / "ergon_core/ergon_core/core/persistence/graph/status_conventions.py",
    }

    for path in (ROOT / "ergon_core/ergon_core/core").rglob("*.py"):
        if path in allowed:
            continue
        text = path.read_text()
        for snippet in duplicate_snippets:
            if snippet in text:
                offenders.append(f"{path.relative_to(ROOT)} duplicates {snippet}")

    assert offenders == []
```

- [ ] **Step 2: Run the new test and verify it fails**

Run: `uv run pytest tests/unit/architecture/test_core_schema_sources.py::test_graph_status_literals_are_defined_only_in_status_conventions -v`

Expected: FAIL because `task_inspection_dto.py` duplicates the node status `Literal`.

- [ ] **Step 3: Add canonical helpers to `status_conventions.py`**

Update `ergon_core/ergon_core/core/persistence/graph/status_conventions.py`:

```python
NodeStatus = Literal["pending", "ready", "running", "completed", "failed", "cancelled", "blocked"]

NON_AUTONOMOUS_STATUSES = TERMINAL_STATUSES | frozenset({BLOCKED})


def is_terminal_node_status(status: str) -> bool:
    return status in TERMINAL_STATUSES


def is_blockable_node_status(status: str) -> bool:
    return status != RUNNING and status not in TERMINAL_STATUSES
```

Keep `EdgeStatus` in the same file. Do not move graph statuses to `shared/enums.py`; graph status intentionally remains string-backed because `RunGraphNode.status` is free-form at the database layer.

- [ ] **Step 4: Replace `SubtaskStatus` with `NodeStatus` at the field boundary**

Update `ergon_core/ergon_core/core/runtime/services/task_inspection_dto.py`:

```python
from ergon_core.core.persistence.graph.status_conventions import NodeStatus
from ergon_core.core.persistence.shared.types import NodeId
from pydantic import BaseModel
```

Change the model field from:

```python
status: SubtaskStatus
```

to:

```python
status: NodeStatus
```

Delete the `SubtaskStatus` name entirely. If any downstream call site imports `SubtaskStatus`, update that call site to import `NodeStatus` from `status_conventions.py` instead. The goal is one concept name for graph-node lifecycle state.

- [ ] **Step 5: Run focused tests**

Run: `uv run pytest tests/unit/architecture/test_core_schema_sources.py tests/unit/state/test_subtask_lifecycle_toolkit.py tests/unit/runtime/test_workflow_service.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tests/unit/architecture/test_core_schema_sources.py ergon_core/ergon_core/core/persistence/graph/status_conventions.py ergon_core/ergon_core/core/runtime/services/task_inspection_dto.py
git commit -m "Consolidate graph status conventions"
```

---

### Task 2: Separate Graph Status From Task Execution Status In Propagation

**Files:**
- Modify: `tests/unit/runtime/test_propagation_contracts.py`
- Modify: `ergon_core/ergon_core/core/runtime/execution/propagation.py`
- Modify: `ergon_core/ergon_core/core/runtime/services/task_propagation_service.py`
- Modify: `ergon_core/ergon_core/core/runtime/services/task_execution_service.py`
- Modify: `ergon_core/ergon_core/core/runtime/services/workflow_initialization_service.py`

- [ ] **Step 1: Write tests for graph-node status constants at every graph write boundary**

Add `tests/unit/runtime/test_propagation_contracts.py`:

```python
from ergon_core.core.persistence.graph import status_conventions as graph_status
from ergon_core.core.runtime.execution import propagation
from ergon_core.core.runtime.services import task_execution_service, task_propagation_service
from ergon_core.core.runtime.services import workflow_initialization_service


def _source(module: object) -> str:
    loader = getattr(module, "__loader__")
    source = loader.get_source(module.__name__)
    assert source is not None
    return source


def test_graph_writers_do_not_use_task_execution_status_for_node_status() -> None:
    modules = [
        propagation,
        task_execution_service,
        task_propagation_service,
        workflow_initialization_service,
    ]
    forbidden_snippets = (
        "new_status=TaskExecutionStatus.",
        "initial_node_status=TaskExecutionStatus.",
    )

    offenders = [
        f"{module.__name__}: {snippet}"
        for module in modules
        for snippet in forbidden_snippets
        if snippet in _source(module)
    ]

    assert offenders == []
    assert graph_status.READY == "ready"
```

This is an architecture test. It is intentionally string-based because the cleanup goal is import-boundary clarity.

- [ ] **Step 2: Run the test and verify it fails**

Run: `uv run pytest tests/unit/runtime/test_propagation_contracts.py::test_graph_writers_do_not_use_task_execution_status_for_node_status -v`

Expected: FAIL because `propagation.py`, `task_propagation_service.py`, `task_execution_service.py`, and `workflow_initialization_service.py` currently use `TaskExecutionStatus` values while writing graph-node status.

- [ ] **Step 3: Update propagation imports**

In `ergon_core/ergon_core/core/runtime/execution/propagation.py`, replace direct status imports with a module alias:

```python
from ergon_core.core.persistence.graph import status_conventions as graph_status
```

Remove `TaskExecutionStatus` from `propagation.py` if it becomes unused. This module operates on `RunGraphNode` / `RunGraphEdge`, so all graph-node writes and graph-node comparisons must use `graph_status.*`.

- [ ] **Step 4: Update graph node writes**

Change graph-node status writes:

```python
new_status=graph_status.PENDING
new_status=graph_status.RUNNING
new_status=graph_status.FAILED
new_status=graph_status.BLOCKED
```

Change comparisons:

```python
is_success = terminal_status == graph_status.COMPLETED
if target_node.status == graph_status.RUNNING:
if target_node.status in graph_status.TERMINAL_STATUSES:
is_pending = status == graph_status.PENDING
is_reactivatable_cancelled = status == graph_status.CANCELLED and is_managed_subtask
if all(n is not None and n.status == graph_status.COMPLETED for n in source_nodes):
```

- [ ] **Step 5: Update service calls into propagation**

In `task_propagation_service.py`, call `on_task_completed_or_failed` with graph status constants:

```python
from ergon_core.core.persistence.graph import status_conventions as graph_status
```

Use:

```python
new_status=graph_status.COMPLETED
terminal_status=graph_status.COMPLETED
new_status=graph_status.FAILED
terminal_status=graph_status.FAILED
new_status=graph_status.PENDING
```

- [ ] **Step 6: Update task execution graph writes without changing execution-row writes**

In `task_execution_service.py`, keep `TaskExecutionStatus` for `RunTaskExecution.status` assignments:

```python
execution = RunTaskExecution(
    ...
    status=TaskExecutionStatus.RUNNING,
)
execution.status = TaskExecutionStatus.COMPLETED
execution.status = TaskExecutionStatus.FAILED
```

But change graph-node updates and dashboard node-status emissions to graph status constants:

```python
from ergon_core.core.persistence.graph import status_conventions as graph_status

await self._graph_repo.update_node_status(
    ...,
    new_status=graph_status.RUNNING,
    ...
)

await _emit_task_status(
    ...,
    new_status=graph_status.RUNNING,
    ...
)
```

For finalization events that are explicitly reporting task-node lifecycle state, use:

```python
new_status=graph_status.COMPLETED
old_status=graph_status.RUNNING
new_status=graph_status.FAILED
```

The rule is: `TaskExecutionStatus` belongs to `RunTaskExecution.status`; `graph_status` belongs to `RunGraphNode.status` and dashboard task-node status payloads.

- [ ] **Step 7: Update workflow initialization graph seeding**

In `workflow_initialization_service.py`, keep `RunStatus.EXECUTING` for `RunRecord.status`, but change graph initialization inputs:

```python
from ergon_core.core.persistence.graph import status_conventions as graph_status

graph_repo.initialize_from_definition(
    ...,
    initial_node_status=graph_status.PENDING,
    initial_edge_status=graph_status.EDGE_PENDING,
    ...
)
```

- [ ] **Step 8: Run focused tests**

Run: `uv run pytest tests/unit/runtime/test_propagation_contracts.py tests/unit/runtime/test_workflow_service.py tests/unit/runtime/test_dynamic_task_evaluation_mapping.py tests/unit/runtime/test_failure_error_json.py tests/unit/runtime/test_worker_execute_factory_call.py tests/unit/runtime/test_smoke_topology_drift.py -v`

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add tests/unit/runtime/test_propagation_contracts.py ergon_core/ergon_core/core/runtime/execution/propagation.py ergon_core/ergon_core/core/runtime/services/task_propagation_service.py ergon_core/ergon_core/core/runtime/services/task_execution_service.py ergon_core/ergon_core/core/runtime/services/workflow_initialization_service.py
git commit -m "Use graph status conventions in propagation"
```

---

### Task 3: Align Failure Propagation Contract With BLOCKED Behavior

**Files:**
- Modify: `tests/unit/runtime/test_propagation_contracts.py`
- Modify: `ergon_core/ergon_core/core/runtime/execution/propagation.py`
- Modify: `ergon_core/ergon_core/core/runtime/services/orchestration_dto.py`
- Modify: `ergon_core/ergon_core/core/runtime/services/task_propagation_service.py`
- Modify: `ergon_core/ergon_core/core/runtime/inngest/propagate_execution.py`

- [ ] **Step 1: Add a contract test for no cancellation targets from propagation**

Extend `tests/unit/runtime/test_propagation_contracts.py`:

```python
from ergon_core.core.runtime.services.orchestration_dto import PropagationResult


def test_propagation_result_does_not_expose_invalidated_targets() -> None:
    assert "invalidated_targets" not in PropagationResult.model_fields
```

- [ ] **Step 2: Run the test and verify it fails**

Run: `uv run pytest tests/unit/runtime/test_propagation_contracts.py::test_propagation_result_does_not_expose_invalidated_targets -v`

Expected: FAIL because `PropagationResult` currently has `invalidated_targets`.

- [ ] **Step 3: Simplify `PropagationResult`**

In `orchestration_dto.py`, remove the field:

```python
invalidated_targets: list[UUID] = Field(default_factory=list)
```

Keep:

```python
ready_tasks: list[TaskDescriptor] = Field(default_factory=list)
workflow_terminal_state: WorkflowTerminalState = WorkflowTerminalState.NONE
```

- [ ] **Step 4: Update `on_task_completed_or_failed` return type and docs**

In `propagation.py`, change:

```python
) -> tuple[list[UUID], list[UUID]]:
```

to:

```python
) -> list[UUID]:
```

Update the docstring to say:

```python
"""Handle a node reaching COMPLETED, FAILED, or CANCELLED.

Returns newly ready node IDs.

- COMPLETED: outgoing edges become SATISFIED; targets with all dependencies
  satisfied transition to PENDING for scheduling.
- FAILED / CANCELLED: outgoing edges become INVALIDATED; reachable successors
  transition to BLOCKED unless they are RUNNING or terminal.
"""
```

Remove the local `invalidated: list[UUID] = []` and return only `newly_ready`.

- [ ] **Step 5: Update `TaskPropagationService`**

Change:

```python
newly_ready_node_ids, invalidated_node_ids = await on_task_completed_or_failed(...)
```

to:

```python
newly_ready_node_ids = await on_task_completed_or_failed(...)
```

Remove `invalidated_targets=invalidated_node_ids` from returned `PropagationResult`.

For failure propagation, change:

```python
_ready, invalidated_node_ids = await on_task_completed_or_failed(...)
```

to:

```python
await on_task_completed_or_failed(...)
```

Update docstrings to say failure blocks downstream graph nodes, not cancels them.

- [ ] **Step 6: Remove dead cancellation emission from `propagate_execution.py`**

Remove the import:

```python
TaskCancelledEvent,
```

Remove the loop:

```python
for inv_node_id in propagation.invalidated_targets:
    events.append(...)
```

Keep `TaskCancelledEvent` in `task_events.py`; it is still used by manager/operator cancellation flows.

- [ ] **Step 7: Run focused tests**

Run: `uv run pytest tests/unit/runtime/test_propagation_contracts.py tests/unit/runtime/test_smoke_topology_drift.py tests/unit/runtime/test_dynamic_task_evaluation_mapping.py tests/unit/runtime/test_failed_task_sandbox_cleanup.py -v`

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add tests/unit/runtime/test_propagation_contracts.py ergon_core/ergon_core/core/runtime/execution/propagation.py ergon_core/ergon_core/core/runtime/services/orchestration_dto.py ergon_core/ergon_core/core/runtime/services/task_propagation_service.py ergon_core/ergon_core/core/runtime/inngest/propagate_execution.py
git commit -m "Align propagation contract with blocked successors"
```

---

### Task 4: Consolidate Evaluation Criterion Status

**Files:**
- Modify: `tests/unit/architecture/test_core_schema_sources.py`
- Modify: `ergon_core/ergon_core/core/api/schemas.py`
- Confirm: `ergon_core/ergon_core/core/persistence/telemetry/evaluation_summary.py`

- [ ] **Step 1: Add architecture test for duplicate evaluation status literals**

Add to `tests/unit/architecture/test_core_schema_sources.py`:

```python
def test_eval_criterion_status_literal_is_defined_only_in_evaluation_summary() -> None:
    offenders: list[str] = []
    snippet = 'EvalCriterionStatus = Literal["passed", "failed", "errored", "skipped"]'
    allowed = {
        ROOT / "ergon_core/ergon_core/core/persistence/telemetry/evaluation_summary.py",
    }

    for path in (ROOT / "ergon_core/ergon_core/core").rglob("*.py"):
        if path in allowed:
            continue
        if snippet in path.read_text():
            offenders.append(str(path.relative_to(ROOT)))

    assert offenders == []
```

- [ ] **Step 2: Run the test and verify it fails**

Run: `uv run pytest tests/unit/architecture/test_core_schema_sources.py::test_eval_criterion_status_literal_is_defined_only_in_evaluation_summary -v`

Expected: FAIL because `core/api/schemas.py` currently defines the same alias.

- [ ] **Step 3: Import canonical alias in REST schemas**

In `core/api/schemas.py`, replace:

```python
from typing import Any, Literal
EvalCriterionStatus = Literal["passed", "failed", "errored", "skipped"]
```

with:

```python
from typing import Any
from ergon_core.core.persistence.telemetry.evaluation_summary import EvalCriterionStatus
```

- [ ] **Step 4: Run focused tests**

Run: `uv run pytest tests/unit/architecture/test_core_schema_sources.py tests/unit/runtime/test_evaluation_summary_contracts.py tests/unit/runtime/test_dynamic_task_evaluation_mapping.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/unit/architecture/test_core_schema_sources.py ergon_core/ergon_core/core/api/schemas.py
git commit -m "Use canonical evaluation criterion status"
```

---

### Task 5: Collapse Graph Mutation DTOs Onto One Canonical Record

**Files:**
- Modify: `tests/unit/runtime/test_graph_mutation_contracts.py`
- Modify: `ergon_core/ergon_core/core/runtime/services/graph_dto.py`
- Modify: `ergon_core/ergon_core/core/api/schemas.py`
- Modify: `ergon_core/ergon_core/core/dashboard/event_contracts.py`
- Modify: `ergon_core/ergon_core/core/runtime/services/graph_repository.py`
- Modify: `ergon_core/ergon_core/core/dashboard/emitter.py`

- [ ] **Step 1: Write mutation contract tests**

Create `tests/unit/runtime/test_graph_mutation_contracts.py`:

```python
from uuid import uuid4

from ergon_core.core.dashboard.event_contracts import DashboardGraphMutationEvent
from ergon_core.core.runtime.services.graph_dto import (
    EdgeAddedMutation,
    GraphMutationRecordDto,
    GraphMutationValue,
)
from pydantic import TypeAdapter


def test_rest_and_dashboard_mutations_share_graph_mutation_record_payloads() -> None:
    run_id = uuid4()
    mutation_id = uuid4()
    edge_id = uuid4()
    source_id = uuid4()
    target_id = uuid4()

    payload = EdgeAddedMutation(
        source_node_id=source_id,
        target_node_id=target_id,
        status="pending",
    )

    TypeAdapter(GraphMutationValue).validate_python(payload.model_dump(mode="json"))

    record = GraphMutationRecordDto(
        id=mutation_id,
        run_id=run_id,
        sequence=1,
        mutation_type="edge.added",
        target_type="edge",
        target_id=edge_id,
        actor="test",
        old_value=None,
        new_value=payload,
        reason=None,
        created_at="2026-04-28T00:00:00Z",
    )
    dashboard = DashboardGraphMutationEvent(
        mutation=record,
    )

    assert dashboard.mutation == record
    assert record.new_value == payload
```

- [ ] **Step 2: Run the test and verify it fails**

Run: `uv run pytest tests/unit/runtime/test_graph_mutation_contracts.py::test_rest_and_dashboard_mutations_share_graph_mutation_record_payloads -v`

Expected: FAIL because `GraphMutationRecordDto` does not exist yet and `DashboardGraphMutationEvent` currently duplicates mutation fields instead of wrapping one canonical record.

- [ ] **Step 3: Make edge mutation IDs consistent with graph DTO IDs**

In `graph_dto.py`, change:

```python
source_node_id: str
target_node_id: str
```

to:

```python
source_node_id: NodeId
target_node_id: NodeId
```

for both `EdgeAddedMutation` and `EdgeRemovedMutation`.

If JSON serialization needs strings, keep conversion at the API/dashboard serialization boundary with `model_dump(mode="json")`; do not weaken the canonical payload type.

- [ ] **Step 4: Add canonical mutation record DTO**

In `graph_dto.py`, add:

```python
from datetime import datetime


class GraphMutationRecordDto(BaseModel):
    """Append-only graph mutation record with a typed mutation payload."""

    model_config = {"frozen": True}

    id: UUID
    run_id: RunId
    sequence: int
    mutation_type: MutationType
    target_type: GraphTargetType
    target_id: UUID
    actor: str
    old_value: GraphMutationValue | None
    new_value: GraphMutationValue
    reason: str | None
    created_at: datetime
```

- [ ] **Step 5: Replace REST mutation DTO with canonical record**

In `core/api/schemas.py`, remove `RunGraphMutationDto` and import:

```python
from ergon_core.core.runtime.services.graph_dto import GraphMutationRecordDto
```

Update `core/api/runs.py` and `run_read_service.py` so `/runs/{run_id}/mutations` returns `list[GraphMutationRecordDto]`. Keep JSON stringification at FastAPI/Pydantic serialization, not in a second REST DTO.

- [ ] **Step 6: Collapse dashboard event to a thin envelope**

In `event_contracts.py`, replace duplicated mutation fields with:

```python
from ergon_core.core.runtime.services.graph_dto import GraphMutationRecordDto


class DashboardGraphMutationEvent(InngestEventContract):
    name: ClassVar[str] = "dashboard/graph.mutation"

    mutation: GraphMutationRecordDto
```

If frontend contract compatibility requires top-level fields for one release, stop and ask before adding a compatibility shim; the requested direction is to reduce duplicate DTOs.

- [ ] **Step 7: Update repository/emitter conversion code**

Search for mutation construction:

```bash
rg "EdgeAddedMutation|EdgeRemovedMutation|GraphMutationValue|DashboardGraphMutationEvent|RunGraphMutationDto|GraphMutationRecordDto" ergon_core/ergon_core/core tests -n
```

Update `_to_mutation_dto` / mutation read paths to produce `GraphMutationRecordDto`. Update `dashboard/emitter.py` to construct `DashboardGraphMutationEvent(mutation=record)` instead of copying fields. Update call sites to pass UUID/`NodeId` values into `EdgeAddedMutation` / `EdgeRemovedMutation`. Use `model_dump(mode="json")` only when writing JSON columns or sending wire payloads.

- [ ] **Step 8: Run focused mutation/dashboard tests**

Run: `uv run pytest tests/unit/runtime/test_graph_mutation_contracts.py tests/unit/dashboard/test_event_contract_types.py tests/unit/architecture/test_model_field_descriptions.py -v`

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add tests/unit/runtime/test_graph_mutation_contracts.py ergon_core/ergon_core/core/runtime/services/graph_dto.py ergon_core/ergon_core/core/api/schemas.py ergon_core/ergon_core/core/dashboard/event_contracts.py ergon_core/ergon_core/core/runtime/services/graph_repository.py ergon_core/ergon_core/core/dashboard/emitter.py
git commit -m "Unify graph mutation payload contracts"
```

---

### Task 6: Collapse Task Node Projections Where Shapes Are Accidental

**Files:**
- Modify: `tests/unit/architecture/test_core_schema_sources.py`
- Modify: `ergon_core/ergon_core/core/api/schemas.py`
- Modify: `ergon_core/ergon_core/core/api/runs.py`
- Modify: `ergon_core/ergon_core/core/runtime/services/graph_dto.py`
- Modify: `ergon_core/ergon_core/core/runtime/services/workflow_dto.py`
- Modify: `ergon_core/ergon_core/core/runtime/services/workflow_service.py`
- Modify: `ergon_core/ergon_core/core/dashboard/event_contracts.py`
- Modify: `ergon_core/ergon_core/core/runtime/inngest/start_workflow.py`

- [ ] **Step 1: Add tests for task-node DTO collapse**

Add to `tests/unit/architecture/test_core_schema_sources.py`:

```python
def test_run_task_dto_does_not_label_worker_slug_as_name() -> None:
    path = ROOT / "ergon_core/ergon_core/core/api/schemas.py"
    text = path.read_text()
    assert "assigned_worker_name" not in text
    assert "assigned_worker_slug" in text


def test_workflow_task_ref_does_not_duplicate_graph_task_ref() -> None:
    path = ROOT / "ergon_core/ergon_core/core/runtime/services/workflow_dto.py"
    assert "class WorkflowTaskRef" not in path.read_text()
```

- [ ] **Step 2: Run the test and verify it fails**

Run: `uv run pytest tests/unit/architecture/test_core_schema_sources.py::test_run_task_dto_does_not_label_worker_slug_as_name tests/unit/architecture/test_core_schema_sources.py::test_workflow_task_ref_does_not_duplicate_graph_task_ref -v`

Expected: FAIL because `RunTaskDto` currently has `assigned_worker_name` and `workflow_dto.py` currently defines `WorkflowTaskRef`.

- [ ] **Step 3: Rename REST task field to match its actual value**

In `core/api/schemas.py`, change:

```python
assigned_worker_name: str | None = None
```

to:

```python
assigned_worker_slug: str | None = None
```

In `core/api/runs.py`, change the `_build_task_map` assignment from `assigned_worker_name=...` to `assigned_worker_slug=...`.

- [ ] **Step 4: Introduce one canonical lightweight graph task ref**

In `graph_dto.py`, add:

```python
class GraphTaskRef(BaseModel):
    """Lightweight task-node reference for workflow/tool projections."""

    model_config = {"frozen": True}

    node_id: NodeId
    task_slug: str
    status: NodeStatus
    level: int
    parent_node_id: NodeId | None = None
    assigned_worker_slug: str | None = None
```

Import `NodeStatus` from `status_conventions.py`.

- [ ] **Step 5: Replace `WorkflowTaskRef` with `GraphTaskRef`**

In `workflow_dto.py`, remove `WorkflowTaskRef` and import:

```python
from ergon_core.core.runtime.services.graph_dto import GraphTaskRef
```

Update fields:

```python
source: GraphTaskRef
target: GraphTaskRef
task: GraphTaskRef
task: GraphTaskRef | None = None
```

In `workflow_service.py`, update `_task_ref` to return `GraphTaskRef`.

- [ ] **Step 6: Keep map-vs-tree containers, but share task-node semantics**

Add or update comments near `RunTaskDto`:

```python
class RunTaskDto(CamelModel):
    """REST projection of RunGraphNode for run detail pages.

    This is not the canonical graph schema; graph semantics live in
    runtime/services/graph_dto.py and persistence/graph/status_conventions.py.
    """
```

Keep `RunSnapshotDto.tasks: dict[str, RunTaskDto]` and `DashboardWorkflowStartedEvent.task_tree: TaskTreeNode` because map and tree containers are genuinely different. But align their field names and statuses with `GraphTaskRef`: `assigned_worker_slug` means slug, `status` is `NodeStatus`, and dependency/child fields are container-specific additions rather than new task-node semantics.

- [ ] **Step 7: Run focused API/dashboard/workflow tests**

Run: `uv run pytest tests/unit/architecture/test_core_schema_sources.py tests/unit/cli/test_workflow_cli.py tests/unit/dashboard/test_event_contract_types.py tests/unit/state/test_workflow_cli_tool.py -v`

Expected: PASS. If frontend TypeScript expects `assignedWorkerName`, update that in a separate frontend-compatible task rather than sneaking it into this backend cleanup.

- [ ] **Step 8: Commit**

```bash
git add tests/unit/architecture/test_core_schema_sources.py ergon_core/ergon_core/core/api/schemas.py ergon_core/ergon_core/core/api/runs.py ergon_core/ergon_core/core/runtime/services/graph_dto.py ergon_core/ergon_core/core/runtime/services/workflow_dto.py ergon_core/ergon_core/core/runtime/services/workflow_service.py ergon_core/ergon_core/core/dashboard/event_contracts.py ergon_core/ergon_core/core/runtime/inngest/start_workflow.py
git commit -m "Collapse duplicate task node projections"
```

---

### Task 7: Reuse CancelCause Instead Of Local Literal Subsets

**Files:**
- Modify: `tests/unit/architecture/test_core_schema_sources.py`
- Modify: `ergon_core/ergon_core/core/runtime/events/task_events.py`
- Modify: `ergon_core/ergon_core/core/runtime/services/subtask_cancellation_service.py`
- Modify: any caller that accepts the same literal subset.

- [ ] **Step 1: Add architecture test for local cancel-cause literals**

Add to `tests/unit/architecture/test_core_schema_sources.py`:

```python
def test_cancel_cause_literals_live_in_task_events() -> None:
    offenders: list[str] = []
    snippets = (
        'Literal["parent_terminal", "dep_invalidated"]',
        'Literal["dep_invalidated", "parent_terminal"]',
    )
    allowed = {
        ROOT / "ergon_core/ergon_core/core/runtime/events/task_events.py",
    }

    for path in (ROOT / "ergon_core/ergon_core/core").rglob("*.py"):
        if path in allowed:
            continue
        text = path.read_text()
        for snippet in snippets:
            if snippet in text:
                offenders.append(f"{path.relative_to(ROOT)} duplicates cancel cause subset")

    assert offenders == []
```

- [ ] **Step 2: Run the test and verify it fails**

Run: `uv run pytest tests/unit/architecture/test_core_schema_sources.py::test_cancel_cause_literals_live_in_task_events -v`

Expected: FAIL if `subtask_cancellation_service.py` still defines a local subset literal.

- [ ] **Step 3: Add named subset aliases in `task_events.py`**

In `task_events.py`, below `CancelCause`, add:

```python
PropagationCancelCause = Literal["parent_terminal", "dep_invalidated"]
```

This keeps narrower service typing but centralizes the strings.

- [ ] **Step 4: Import the subset alias in services**

In `subtask_cancellation_service.py`, replace the local `Literal[...]` import/annotation with:

```python
from ergon_core.core.runtime.events.task_events import PropagationCancelCause
```

Use:

```python
cause: PropagationCancelCause
```

- [ ] **Step 5: Run focused cancellation tests**

Run: `uv run pytest tests/unit/runtime/test_failed_task_sandbox_cleanup.py tests/unit/runtime/test_dynamic_task_evaluation_mapping.py tests/unit/state/test_subtask_lifecycle_toolkit.py tests/unit/architecture/test_core_schema_sources.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tests/unit/architecture/test_core_schema_sources.py ergon_core/ergon_core/core/runtime/events/task_events.py ergon_core/ergon_core/core/runtime/services/subtask_cancellation_service.py
git commit -m "Centralize task cancellation causes"
```

---

### Task 8: Collapse Context Event Snapshot DTOs Onto Typed Payloads

**Files:**
- Modify: `tests/unit/runtime/test_context_event_contracts.py`
- Modify: `ergon_core/ergon_core/core/api/schemas.py`
- Modify: `ergon_core/ergon_core/core/api/runs.py`
- Modify: `ergon_core/ergon_core/core/dashboard/event_contracts.py`
- Modify: `ergon_core/ergon_core/core/dashboard/emitter.py`

- [ ] **Step 1: Write a context event DTO sharing test**

Create `tests/unit/runtime/test_context_event_contracts.py`:

```python
from uuid import uuid4

from ergon_core.core.api.schemas import RunContextEventDto
from ergon_core.core.dashboard.event_contracts import DashboardContextEventEvent
from ergon_core.core.persistence.context.event_payloads import AssistantTextPayload


def test_rest_and_dashboard_context_events_share_typed_payload_shape() -> None:
    payload = AssistantTextPayload(text="hello")
    common = {
        "id": uuid4(),
        "run_id": uuid4(),
        "task_execution_id": uuid4(),
        "task_node_id": uuid4(),
        "worker_binding_key": "worker",
        "sequence": 1,
        "event_type": "assistant_text",
        "payload": payload,
        "created_at": "2026-04-28T00:00:00Z",
        "started_at": None,
        "completed_at": None,
    }

    rest = RunContextEventDto.model_validate(common)
    dashboard = DashboardContextEventEvent.model_validate(common)

    assert rest.payload == dashboard.payload
    assert rest.event_type == dashboard.event_type
```

- [ ] **Step 2: Run the test and verify it fails**

Run: `uv run pytest tests/unit/runtime/test_context_event_contracts.py::test_rest_and_dashboard_context_events_share_typed_payload_shape -v`

Expected: FAIL because `RunContextEventDto` currently uses `event_type: str` and `payload: dict[str, Any]`, while dashboard uses `ContextEventType` and `ContextEventPayload`.

- [ ] **Step 3: Type REST context event DTO with canonical event payloads**

In `core/api/schemas.py`, import:

```python
from ergon_core.core.persistence.context.event_payloads import (
    ContextEventPayload,
    ContextEventType,
)
```

Update:

```python
event_type: ContextEventType
payload: ContextEventPayload
```

- [ ] **Step 4: Update REST context event construction**

In `core/api/runs.py`, when building `RunContextEventDto`, validate payload with the canonical discriminated payload type. If rows already store dict payloads, use the same validation path as dashboard emitter uses rather than passing raw dicts through REST.

- [ ] **Step 5: Decide whether to fully collapse class names**

If `RunContextEventDto` and `DashboardContextEventEvent` now have the same fields except event `name`, move the common fields into a shared model:

```python
class ContextEventDto(CamelModel or BaseModel):
    ...
```

Use that model directly in REST and embed it in the dashboard event envelope. If camelCase REST output makes a shared class awkward, keep the two envelope classes but require both to use `ContextEventType` and `ContextEventPayload`.

- [ ] **Step 6: Run focused tests**

Run: `uv run pytest tests/unit/runtime/test_context_event_contracts.py tests/unit/dashboard/test_event_contract_types.py tests/unit/architecture/test_model_field_descriptions.py -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add tests/unit/runtime/test_context_event_contracts.py ergon_core/ergon_core/core/api/schemas.py ergon_core/ergon_core/core/api/runs.py ergon_core/ergon_core/core/dashboard/event_contracts.py ergon_core/ergon_core/core/dashboard/emitter.py
git commit -m "Share typed context event payload schemas"
```

---

### Task 9: Add Mapping Guard Between Generation Parts And Context Events

**Files:**
- Modify: `tests/unit/builtins/common/test_transcript_adapters.py`
- Modify: `ergon_builtins/ergon_builtins/common/llm_context/adapters/pydantic_ai.py` only if the test reveals unmapped kinds.

- [ ] **Step 1: Add explicit adapter coverage for vocabulary mapping**

In `tests/unit/builtins/common/test_transcript_adapters.py`, add a test that documents the intended split between `core.generation` kebab-case `part_kind` and context event snake-case `event_type`:

```python
from ergon_core.core.generation import TextPart, ThinkingPart, ToolCallPart, ToolReturnPart
from ergon_core.core.persistence.context.event_payloads import ContextEventType


def test_generation_part_kinds_have_context_event_counterparts() -> None:
    assert TextPart(content="x").part_kind == "text"
    assert ThinkingPart(content="x").part_kind == "thinking"
    assert ToolCallPart(tool_name="t", tool_call_id="1", args={}).part_kind == "tool-call"
    assert ToolReturnPart(tool_call_id="1", tool_name="t", content="ok").part_kind == "tool-return"

    assert "assistant_text" in ContextEventType.__args__
    assert "thinking" in ContextEventType.__args__
    assert "tool_call" in ContextEventType.__args__
    assert "tool_result" in ContextEventType.__args__
```

- [ ] **Step 2: Run the test**

Run: `uv run pytest tests/unit/builtins/common/test_transcript_adapters.py::test_generation_part_kinds_have_context_event_counterparts -v`

Expected: PASS if the current split is intentional and covered; FAIL if any expected context event value has drifted.

- [ ] **Step 3: Fix adapter mapping only if the test fails**

If the test fails because context event values changed, update `ergon_builtins/ergon_builtins/common/llm_context/adapters/pydantic_ai.py` to map the actual canonical context event types. Do not merge generation parts and context events into one model family.

- [ ] **Step 4: Run focused adapter tests**

Run: `uv run pytest tests/unit/builtins/common/test_transcript_adapters.py tests/unit/persistence/test_context_event_repository.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/unit/builtins/common/test_transcript_adapters.py ergon_builtins/ergon_builtins/common/llm_context/adapters/pydantic_ai.py
git commit -m "Guard generation to context event mapping"
```

---

### Task 10: Final Architecture Sweep

**Files:**
- Modify: `tests/unit/architecture/test_core_schema_sources.py`
- Modify: `docs/superpowers/plans/2026-04-28-core-schema-deduplication.md` only if implementation reveals a necessary correction.

- [ ] **Step 1: Add a broad forbidden-duplication guard**

Add to `tests/unit/architecture/test_core_schema_sources.py`:

```python
def test_core_schema_source_imports_are_directional() -> None:
    forbidden_pairs = {
        "ergon_core.core.api.schemas": (
            "EvalCriterionStatus = Literal",
            "GraphMutationValue =",
        ),
        "ergon_core.core.dashboard.event_contracts": (
            "GraphMutationValue =",
            "CancelCause = Literal",
        ),
    }

    offenders: list[str] = []
    for module_path, snippets in forbidden_pairs.items():
        path = ROOT / (module_path.replace(".", "/") + ".py")
        text = path.read_text()
        for snippet in snippets:
            if snippet in text:
                offenders.append(f"{path.relative_to(ROOT)} contains local source {snippet!r}")

    assert offenders == []
```

- [ ] **Step 2: Run the full architecture test set**

Run: `uv run pytest tests/unit/architecture -v`

Expected: PASS.

- [ ] **Step 3: Run focused runtime/schema tests**

Run:

```bash
uv run pytest \
  tests/unit/runtime/test_workflow_service.py \
  tests/unit/runtime/test_dynamic_task_evaluation_mapping.py \
  tests/unit/runtime/test_evaluation_summary_contracts.py \
  tests/unit/dashboard/test_event_contract_types.py \
  tests/unit/builtins/common/test_transcript_adapters.py \
  tests/unit/architecture/test_model_field_descriptions.py \
  -v
```

Expected: PASS.

- [ ] **Step 4: Search for remaining duplicate literals**

Run:

```bash
rg 'Literal\["pending", "ready", "running", "completed", "failed", "cancelled", "blocked"\]|EvalCriterionStatus = Literal|invalidated_targets|assigned_worker_name|Literal\["parent_terminal", "dep_invalidated"\]' ergon_core tests
```

Expected output may include only:

```text
ergon_core/ergon_core/core/persistence/graph/status_conventions.py
ergon_core/ergon_core/core/persistence/telemetry/evaluation_summary.py
tests/unit/architecture/test_core_schema_sources.py
```

If other production files appear, either import the canonical alias or explain in a code comment why the duplicate-looking concept is distinct.

- [ ] **Step 5: Run lints for touched files**

Use Cursor lints for:

```text
ergon_core/ergon_core/core/persistence/graph/status_conventions.py
ergon_core/ergon_core/core/runtime/execution/propagation.py
ergon_core/ergon_core/core/runtime/services
ergon_core/ergon_core/core/api/schemas.py
ergon_core/ergon_core/core/dashboard/event_contracts.py
tests/unit/architecture/test_core_schema_sources.py
```

Expected: no new diagnostics in touched files.

- [ ] **Step 6: Commit final guard changes**

```bash
git add tests/unit/architecture/test_core_schema_sources.py
git commit -m "Guard core schema source ownership"
```

---

## Execution Notes

- Do not collapse legitimate transport envelopes into one giant schema. Do collapse duplicated payload bodies: `WorkflowTaskRef` should disappear in favor of `GraphTaskRef`; REST/dashboard task containers can remain map/tree envelopes only if their field semantics align with the canonical graph task ref.
- Do remove duplicate domain definitions. If two modules need the same literal values, one imports from the source-of-truth module.
- Keep table models free-form where the database intentionally allows extension, but make runtime conventions explicit through aliases and constants.
- Keep REST/dashboard serialization at the boundary. Canonical Python DTOs can use UUID/NewType fields; wire models can stringify with `model_dump(mode="json")`.
- Avoid compatibility facades. If a module owns a concept, import it directly from that module.

## Self-Review

- Spec coverage: high-priority graph status duplication, evaluation status duplication, stale propagation contract, graph mutation DTO collapse, task-node DTO collapse, context-event DTO typing, cancel-cause duplication, and generation/context event vocabulary mapping are each covered by a task.
- Placeholder scan: no task contains unresolved placeholder markers or an unspecified "add tests" instruction; every task names files and commands.
- Type consistency: graph status aliases live in `status_conventions.py`, evaluation status in `evaluation_summary.py`, mutation payload body in `graph_dto.py`, and cancel-cause aliases in `task_events.py` throughout the plan.
