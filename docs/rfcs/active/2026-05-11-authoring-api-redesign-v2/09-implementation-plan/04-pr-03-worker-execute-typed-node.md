# PR 3 — Worker-Execute Uses Typed Run Nodes

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` or
> `superpowers:executing-plans` to implement this plan task-by-task.

**Goal:** Make worker execution prepare and run from `graph_repo.node(...).task`
instead of rebuilding static tasks from definition rows.

**Architecture:** The runtime path prefers the typed run-node boundary from
PR 2. A single legacy fallback remains only for tests or callers that have
not yet been converted.

**Tech Stack:** Python async jobs, SQLModel repositories, pytest runtime
tests, textual architecture guards.

---

## Files

**Modify:**

```text
ergon_core/ergon_core/core/application/tasks/execution.py
ergon_core/ergon_core/core/application/workflows/orchestration.py
ergon_core/ergon_core/core/application/jobs/worker_execute.py
ergon_core/ergon_core/core/application/jobs/models.py
ergon_core/tests/unit/runtime/test_worker_execute_stream_contract.py
ergon_core/tests/unit/runtime/test_definition_task_payload_typing.py
ergon_core/tests/unit/architecture/test_runtime_read_boundaries.py
```

## Current State

`TaskExecutionService.prepare()` branches:

```python
if command.node_id is not None:
    return await self._prepare_graph_native(command)
return await self._prepare_definition(command)
```

`worker_execute.py` then reads `RunGraphNode` by `payload.node_id` and, for
static nodes, calls `DefinitionRepository().task_with_instance(...)`.

## Target State For This PR

Preparation returns a payload keyed by run node identity, and
`worker_execute.py` starts with:

```python
with get_session() as session:
    node = await WorkflowGraphRepository().node(
        session,
        run_id=payload.run_id,
        task_id=payload.task_id,
    )
task = node.task
```

No static/dynamic branch exists in the job body. The `await` is required
because `WorkflowGraphRepository.node` becomes async in PR 2; the
`get_session()` context manager stays sync (it just opens a DB session)
but the call inside it is awaited.

## Task 1: Reshape Prepared Execution DTO

**Files:**

- Modify: `ergon_core/ergon_core/core/application/workflows/orchestration.py`

- [x] **Step 1: Keep transitional identity fields but make `task_id` canonical**

Update `PreparedTaskExecution` to include:

```python
run_id: UUID
definition_id: UUID
task_id: UUID
node_id: UUID
definition_task_id: UUID | None = None
task_slug: str
task_description: str
benchmark_type: str
assigned_worker_slug: str | None = None
worker_type: str | None = None
model_target: str | None = None
execution_id: UUID
```

During transition, `task_id` is `definition_task_id` for static nodes and
`node_id` for dynamic nodes. PR 11 removes `node_id` and
`definition_task_id`.

## Task 2: Prefer Graph-Native Preparation

**Files:**

- Modify: `ergon_core/ergon_core/core/application/tasks/execution.py`

- [x] **Step 1: Change `prepare` branch order**

Replace:

```python
if command.node_id is not None:
    return await self._prepare_graph_native(command)
return await self._prepare_definition(command)
```

with:

```python
return await self._prepare_run_node(command)
```

- [x] **Step 2: Add `_prepare_run_node`**

```python
async def _prepare_run_node(self, command: PrepareTaskExecutionCommand) -> PreparedTaskExecution:
    lookup_id = command.node_id or command.task_id
    if lookup_id is None:
        raise ConfigurationError(
            "Task preparation requires node_id or task_id",
            run_id=command.run_id,
            task_id=None,
        )
    with get_session() as session:
        view = await self._graph_repo.node(session, run_id=command.run_id, task_id=lookup_id)
        node = session.get(RunGraphNode, view.node_id)
        if node is None:
            raise ConfigurationError(
                f"RunGraphNode {view.node_id} not found",
                run_id=command.run_id,
                task_id=lookup_id,
            )
        definition = require_not_none(
            session.get(ExperimentDefinition, command.definition_id),
            f"Definition {command.definition_id} not found",
        )
        execution = RunTaskExecution(
            run_id=command.run_id,
            node_id=view.node_id,
            definition_task_id=view.definition_task_id,
            attempt_number=self._task_execution_repo.next_attempt_for_node(
                session, command.run_id, view.node_id
            ),
            status=TaskExecutionStatus.RUNNING,
            started_at=utcnow(),
        )
        session.add(execution)
        session.flush()
        await self._graph_repo.update_node_status(
            session,
            run_id=command.run_id,
            node_id=view.node_id,
            new_status=graph_status.RUNNING,
            meta=MutationMeta(actor="task-execution-service", reason=f"prepare: {execution.id}"),
        )
        session.commit()

    await _emit_task_status(
        run_id=command.run_id,
        node_id=view.node_id,
        task_slug=view.task.task_slug,
        new_status=graph_status.RUNNING,
        old_status=None,
    )
    return PreparedTaskExecution(
        run_id=command.run_id,
        definition_id=command.definition_id,
        task_id=view.task_id,
        node_id=view.node_id,
        definition_task_id=view.definition_task_id,
        task_slug=view.task.task_slug,
        task_description=view.task.description,
        benchmark_type=definition.benchmark_type,
        assigned_worker_slug=node.assigned_worker_slug,
        worker_type=node.assigned_worker_slug,
        model_target=None,
        execution_id=execution.id,
    )
```

- [x] **Step 3: Rename old method**

Rename `_prepare_definition` to `_prepare_legacy_definition` and leave it
unused. PR 11 deletes it. Keeping the method available makes rollback
explicit during this PR.

## Task 3: Update Worker-Execute Job Body

**Files:**

- Modify: `ergon_core/ergon_core/core/application/jobs/worker_execute.py`

- [x] **Step 1: Remove direct definition imports**

Delete these imports from the job:

```python
from ergon_core.core.application.components.catalog import ComponentCatalogService
from ergon_core.core.application.experiments.repository import DefinitionRepository
from ergon_core.core.persistence.graph.models import RunGraphNode
```

Add:

```python
from ergon_core.core.application.graph.repository import WorkflowGraphRepository
```

- [x] **Step 2: Replace task construction block**

Replace the current block that builds `worker`, `node`, `task_payload`, and
`Task(...)` with:

```python
with get_session() as session:
    node = await WorkflowGraphRepository().node(
        session,
        run_id=payload.run_id,
        task_id=payload.task_id,
    )
task = node.task
```

Until PR 5, old snapshots do not carry `task.worker`. For this PR keep
worker registry construction in a helper:

```python
worker = _worker_from_payload_bridge(payload)
```

Implement bridge:

```python
def _worker_from_payload_bridge(payload: WorkerExecuteJobRequest) -> Worker:
    catalog = ComponentCatalogService()
    with get_session() as session:
        return catalog.build_worker(
            session,
            slug=payload.worker_type,
            name=payload.assigned_worker_slug,
            model=payload.model_target,
        )
```

This bridge is deleted in PR 5 or PR 11 when `task.worker` is always
present.

## Task 4: Architecture Guard

**Files:**

- Create: `ergon_core/tests/unit/architecture/test_runtime_read_boundaries.py`

- [x] **Step 1: Add guard**

```python
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]


def test_worker_execute_does_not_read_definition_repository() -> None:
    text = (
        ROOT
        / "ergon_core/ergon_core/core/application/jobs/worker_execute.py"
    ).read_text()
    assert "DefinitionRepository" not in text
    assert "task_with_instance" not in text
    assert "ExperimentDefinitionTask" not in text
```

- [x] **Step 2: Run tests**

```bash
uv run pytest ergon_core/tests/unit/architecture/test_runtime_read_boundaries.py \
  ergon_core/tests/unit/runtime/test_worker_execute_stream_contract.py -q
```

## Task 5: Flip XFails Landed By This PR

**Files:**

- Modify: `ergon_core/tests/unit/architecture/test_v2_final_state_ledger.py`
- Modify: `ergon_core/tests/unit/architecture/test_dead_path_audit.py`
- Modify: `ergon_core/tests/unit/runtime/test_walkthrough_smoketest.py`

This PR flips the worker-execute run-tier-only invariant green. Three
ledger entries must drop their xfail markers in this commit:

- [x] **Step 1: Remove `worker_execute_imports_only_run_tier` from `_XFAIL_BY_NAME`**

In `test_v2_final_state_ledger.py`, delete the line:

```python
"worker_execute_imports_only_run_tier": "PR 3 flips worker_execute to run-tier",
```

- [x] **Step 2: Remove `_prepare_definition` from the dead-path xfails**

In `test_dead_path_audit.py`, delete the line:

```python
"_prepare_definition": "PR 3: renamed to _prepare_legacy_definition",
```

(`_prepare_legacy_definition` stays xfailed until PR 11 deletes the
renamed body.)

- [x] **Step 3: Flip `test_worker_execute_reads_task_from_run_tier_only`**

In `test_walkthrough_smoketest.py`, remove the decorator and replace the
`pytest.fail(...)` body with the real assertion. Use a session spy that
records the ORM classes touched during a `worker_execute` invocation;
assert no definition-tier class appears.

- [x] **Step 4: Run the ledgers**

```bash
uv run pytest \
  ergon_core/tests/unit/architecture/test_v2_final_state_ledger.py \
  ergon_core/tests/unit/architecture/test_dead_path_audit.py \
  ergon_core/tests/unit/runtime/test_walkthrough_smoketest.py -q
```

Expected: the three newly-flipped cases PASS; the remaining cases still
XFAIL; no XPASS, no unexpected FAIL.

## PR Ledger

Invariant landed: worker execution uses typed run-node task loading.

Bridge code introduced: `_worker_from_payload_bridge`.

Old path still intentionally alive: worker registry payload fields and
legacy prepare method.

Deletion gate: PR 5 replaces registry worker construction with `task.worker`;
PR 11 deletes legacy prepare.

Tests added or updated: runtime read boundary guard and worker stream tests.

Modules owned by this PR: task execution prep and worker-execute read path.
