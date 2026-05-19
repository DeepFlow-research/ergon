# PR 2 — Typed Run-Node Reconstruction Boundary

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` or
> `superpowers:executing-plans` to implement this plan task-by-task.

**Goal:** Add a repository method that returns a typed `RunGraphNodeView`
with an inflated `Task` reconstructed from `run_graph_nodes.task_json`.
The method is **async** because PR 5's `Sandbox.from_definition` accepts
an optional `sandbox_id` and may attach a live `_runtime` — both
inflation and attach happen inside `node()` so call sites never see a
half-built Task.

**Architecture:** Keep old execution prep alive, but create the v2 boundary:
raw JSON stays inside the repository; job bodies receive typed objects.
The async-ness propagates through `Task.from_definition` and every
caller of `WorkflowGraphRepository.node` (`worker_execute`,
`evaluate_task_run`, `TaskExecutionService.prepare`).

**Tech Stack:** Pydantic v2, SQLModel repository, pytest.

---

## Files

**Modify:**

```text
ergon_core/ergon_core/api/benchmark/task.py
ergon_core/ergon_core/api/worker/worker.py
ergon_core/ergon_core/api/criterion/criterion.py
ergon_core/ergon_core/api/rubric/rubric.py
ergon_core/ergon_core/api/rubric/evaluator.py
ergon_core/ergon_core/core/application/graph/models.py
ergon_core/ergon_core/core/application/graph/repository.py
ergon_core/tests/unit/api/test_task_spec_contract.py
ergon_core/tests/unit/runtime/test_run_graph_task_snapshot.py
```

## Current State

`worker_execute.py` manually builds `Task` by reading `RunGraphNode` and,
for static nodes, following `definition_task_id` back to definition rows.

## Target State For This PR

New call:

```python
node = await graph_repo.node(session, run_id=run_id, task_id=task_id)
task = node.task
# Config-only sandbox: task.sandbox._runtime is None. Caller (or eval
# variant of the call) can pass sandbox_id to get a live runtime:
node_live = await graph_repo.node(
    session, run_id=run_id, task_id=task_id, sandbox_id=execution.sandbox_id,
)
```

The call reads `run_graph_nodes.task_json`, inflates a `Task`, binds
`task.task_id`, optionally attaches a live sandbox runtime when
`sandbox_id` is passed, and returns no raw dicts to the caller.

## Task 1: Add Import-Path Reconstruction Helpers

**Files:**

- Modify: `ergon_core/ergon_core/api/benchmark/task.py`
- Modify: `ergon_core/ergon_core/api/worker/worker.py`

- [x] **Step 1: Add import helper and serialized-form type alias to `task.py`**

```python
from importlib import import_module
from typing import Any
from pydantic import JsonValue, PrivateAttr


type TaskDefinitionJson = dict[str, JsonValue]
"""Serialized form of a Task — `_type`-discriminated JSON written to
`run_graph_nodes.task_json`. Field names are NOT enforced by this type
(the discriminator dispatch in `Task.from_definition` does that); only
the value side is typed, so accidentally stuffing a `datetime` or `UUID`
object into the snapshot fails at typecheck time instead of at
JSON-serialization time. The alias is the named boundary every
`from_definition` classmethod accepts."""


def _import_component(path: str) -> type[Any]:
    module_name, _, qualname = path.partition(":")
    if not module_name or not qualname:
        raise ValueError(f"Component _type must be 'module:qualname', got {path!r}")
    obj: Any = import_module(module_name)
    for part in qualname.split("."):
        # typing: dynamic qualname walk — `part` is a user-controlled
        # discriminator path component, not a typed attribute name.
        obj = getattr(obj, part)
    if not isinstance(obj, type):
        raise TypeError(f"Component _type {path!r} did not resolve to a class")
    return obj
```

`TaskDefinitionJson` is intentionally not a Pydantic model and not a
TypedDict. The shape after the discriminator is dispatched lives on the
Task subclass; trying to mirror it in a parallel typed structure would
duplicate the schema and rot. The boundary type only asserts what's
honest at the boundary: "JSON-shaped, value-side typed."

- [x] **Step 2: Convert `Task` to support runtime identity**

Change `Task.model_config` from frozen to mutable:

```python
model_config = {"frozen": False}
```

Add:

```python
_task_id: UUID | None = PrivateAttr(default=None)

@property
def task_id(self) -> UUID:
    if self._task_id is None:
        raise RuntimeError(
            f"Task {self.task_slug!r} has no task_id; it has not been materialized"
        )
    return self._task_id

@classmethod
async def from_definition(
    cls,
    task_json: TaskDefinitionJson,
    *,
    task_id: UUID,
    sandbox_id: str | None = None,
) -> "Task":
    task_type = task_json.get("_type")
    if not isinstance(task_type, str):
        raise ValueError(
            f"Task snapshot is missing the required `_type` discriminator "
            f"(got {type(task_type).__name__}). Every persisted task must "
            f"carry `_type` — produced by `model_serializer` on Task "
            f"subclasses or by `_definition_task_snapshot` during the PR 1 "
            f"bridge. Soft-defaulting to base `Task` here would silently "
            f"drop the authored worker/sandbox/evaluator bindings."
        )
    TaskCls = _import_component(task_type)
    if TaskCls is TaskSpec:
        # Transitional bridge: PR 5 replaces TaskSpec snapshots with Task JSON.
        spec = TaskSpec.model_validate(task_json)
        instance = Task(
            task_slug=spec.task_slug,
            instance_key=spec.instance_key,
            description=spec.description,
            parent_task_slug=spec.parent_task_slug,
            dependency_task_slugs=spec.dependency_task_slugs,
            evaluator_binding_keys=spec.evaluator_binding_keys,
            task_payload=spec.task_payload,
        )
    else:
        instance = TaskCls.model_validate(task_json)
    object.__setattr__(instance, "_task_id", task_id)
    # sandbox_id is a no-op during PR 2 because TaskSpec snapshots don't
    # carry an object-bound sandbox. PR 5 wires this through to
    # Sandbox.from_definition once Task.sandbox is non-null.
    return instance
```

`from_definition` is **async** even in PR 2 to lock in the signature
PR 5 needs. The async-ness is structural; PR 2's body doesn't await
anything yet, but the protocol contract is the v2 final shape.

During the transition `Task` still has public fields compatible with the
old runtime shape. PR 5 adds object-bound `worker`, `sandbox`, and
`evaluators` and starts honoring the `sandbox_id` parameter.

- [x] **Step 3: Add `Worker.from_definition` and keep `from_buffer`**

In `worker.py`, make `Worker` reconstruction available without deleting
the old dead method yet. Reuse the same serialized-form alias for
consistency across components:

```python
from ergon_core.api.benchmark.task import TaskDefinitionJson as ComponentDefinitionJson


@classmethod
def from_definition(cls, worker_json: ComponentDefinitionJson) -> "Worker":
    worker_type = worker_json.get("_type")
    if not isinstance(worker_type, str):
        raise ValueError(
            f"Worker snapshot is missing the required `_type` "
            f"discriminator (got {type(worker_type).__name__}). Every "
            f"persisted worker must carry `_type`."
        )
    WorkerCls = _import_component(worker_type)
    return cast("Worker", WorkerCls.model_validate(worker_json))
```

Treat `ComponentDefinitionJson` here as the same structural alias as
`TaskDefinitionJson` — different name for readability at the worker
boundary, same underlying `dict[str, JsonValue]`. If a future PR wants
to split the aliases (e.g. add invariants specific to one component
kind), the rename is mechanical.

`Worker.from_buffer` remains until PR 11.

## Task 2: Add `RunGraphNodeView`

**Files:**

- Modify: `ergon_core/ergon_core/core/application/graph/models.py`

- [x] **Step 1: Add model**

```python
from ergon_core.api.benchmark import Task


class RunGraphNodeView(BaseModel):
    model_config = {"frozen": True, "arbitrary_types_allowed": True}

    run_id: UUID
    task_id: UUID
    node_id: UUID
    definition_task_id: UUID | None
    parent_node_id: UUID | None
    status: str
    task: Task
    is_dynamic: bool = False
```

This view carries both `node_id` and `task_id` during transition. PR 11
removes `node_id` from the public runtime identity.

## Task 3: Add `graph_repo.node`

**Files:**

- Modify: `ergon_core/ergon_core/core/application/graph/repository.py`

- [x] **Step 1: Import view**

```python
from ergon_core.api.benchmark import Task
from ergon_core.core.application.graph.models import RunGraphNodeView
```

- [x] **Step 2: Add method**

```python
async def node(
    self,
    session: Session,
    *,
    run_id: UUID,
    task_id: UUID,
    sandbox_id: str | None = None,
) -> RunGraphNodeView:
    row = session.exec(
        select(RunGraphNode).where(
            RunGraphNode.run_id == run_id,
            (RunGraphNode.id == task_id) | (RunGraphNode.definition_task_id == task_id),
        )
    ).first()
    if row is None:
        raise NodeNotFoundError(f"Run graph node {task_id} not found in run {run_id}")

    canonical_task_id = row.definition_task_id or row.id
    task = await Task.from_definition(
        row.task_json,
        task_id=canonical_task_id,
        sandbox_id=sandbox_id,
    )
    return RunGraphNodeView(
        run_id=row.run_id,
        task_id=canonical_task_id,
        node_id=row.id,
        definition_task_id=row.definition_task_id,
        parent_node_id=row.parent_node_id,
        status=row.status,
        task=task,
        is_dynamic=row.is_dynamic,
    )
```

`node()` is async because `Task.from_definition` is async — even in PR 2
where the await does nothing structural. Every call site needs to be
flipped to `await graph_repo.node(...)` in this PR and PR 3.

The OR predicate is transitional. PR 11 changes the lookup to exact
`(run_id, task_id)` after schema finalization.

## Task 4: Tests

**Files:**

- Modify: `ergon_core/tests/unit/runtime/test_run_graph_task_snapshot.py`

- [x] **Step 1: Add reconstruction test**

```python
@pytest.mark.asyncio
async def test_graph_repo_node_inflates_task_from_run_tier(session, run_node_factory):
    row = run_node_factory(
        task_json={
            "_type": "ergon_core.api.benchmark.task:TaskSpec",
            "task_slug": "solve",
            "instance_key": "sample-1",
            "description": "solve it",
            "dependency_task_slugs": [],
            "evaluator_binding_keys": [],
            "task_payload": {},
        }
    )

    view = await WorkflowGraphRepository().node(
        session,
        run_id=row.run_id,
        task_id=row.definition_task_id or row.id,
    )

    assert view.task.task_slug == "solve"
    assert view.task.task_id == (row.definition_task_id or row.id)
```

- [x] **Step 2: Add textual boundary test**

```python
import inspect

from ergon_core.core.application.graph.repository import WorkflowGraphRepository


def test_graph_repo_node_does_not_reference_definition_tier_models() -> None:
    """`graph_repo.node` must hydrate Task from run-tier JSON only.

    PR 2's contract is that the runtime read path goes through
    run_graph_nodes.task_json and never reaches into definition tables.
    This is a textual guard because a subtle import or an inner helper
    that delegates to DefinitionRepository would re-open the read path
    PR 11 is closing.
    """

    source = inspect.getsource(WorkflowGraphRepository.node)
    forbidden = (
        "DefinitionRepository",
        "ExperimentDefinitionTask",
        "task_with_instance",
        "ComponentCatalogService",
    )
    offenders = [symbol for symbol in forbidden if symbol in source]
    assert offenders == [], (
        f"WorkflowGraphRepository.node references definition-tier symbols "
        f"{offenders}; the run-tier read boundary forbids these."
    )
```

- [x] **Step 3: Run focused tests**

```bash
uv run pytest ergon_core/tests/unit/runtime/test_run_graph_task_snapshot.py ergon_core/tests/unit/api/test_task_spec_contract.py -q
```

## Task 5: Flip XFails Landed By This PR

**Files:**

- Modify: `ergon_core/tests/unit/runtime/test_identity_invariants.py`

The PR 1 ledger pre-registered one identity invariant that PR 2 lands.
Remove the corresponding `@pytest.mark.xfail` decorator and verify the
test passes.

- [x] **Step 1: Remove xfail from `test_task_id_propagates_into_runtime_task_instance`**

In `test_identity_invariants.py`, delete the decorator:

```python
@pytest.mark.xfail(
    reason="PR 2: graph_repo.node binds task._task_id from the run-tier row",
    strict=True,
)
```

Replace the `pytest.fail(...)` body with the real assertion:

```python
async def test_task_id_propagates_into_runtime_task_instance(
    session, persisted_definition
):
    from ergon_core.core.application.graph.repository import (
        WorkflowGraphRepository,
    )
    from ergon_core.core.application.workflows.service import prepare_run

    run_id = await prepare_run(session, definition_id=persisted_definition.id)
    repo = WorkflowGraphRepository()

    from sqlmodel import select

    from ergon_core.core.persistence.graph.models import RunGraphNode
    nodes = session.exec(
        select(RunGraphNode).where(RunGraphNode.run_id == run_id)
    ).all()
    for row in nodes:
        canonical_id = row.definition_task_id or row.id
        view = await repo.node(session, run_id=run_id, task_id=canonical_id)
        assert view.task_id == canonical_id
        assert view.task.task_id == canonical_id
```

- [x] **Step 2: Run the ledgers**

```bash
uv run pytest \
  ergon_core/tests/unit/runtime/test_identity_invariants.py \
  ergon_core/tests/unit/architecture/test_v2_final_state_ledger.py \
  ergon_core/tests/unit/architecture/test_dead_path_audit.py -q
```

Expected: two PASS in identity invariants (PR 1 case + the newly-flipped
PR 2 case), the ledgers still XFAIL on every other case. No XPASS.

## PR Ledger

Invariant landed: repository can inflate typed tasks from run-tier JSON.

Bridge code introduced: `TaskSpec` JSON is accepted by
`Task.from_definition`.

Old path still intentionally alive: `_prepare_definition` and
definition-tier static prep.

Deletion gate: PR 3 makes worker execution use this view; PR 11 deletes the
legacy prep fallback.

Tests added or updated: task reconstruction tests and method-source guard.

Modules owned by this PR: API reconstruction and graph repository boundary.
