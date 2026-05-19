# PR 9 — Dynamic Subtasks Are Graph-Native

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` or
> `superpowers:executing-plans` to implement this plan task-by-task.

**Goal:** Make `WorkerContext.spawn_task` write only `run_graph_nodes` with
`is_dynamic=true` and task JSON; no synthetic definition rows.

**Architecture:** Dynamic and static tasks share `graph_repo.node`. The only
difference is row origin.

**Tech Stack:** WorkerContext facade, task management service, graph repo,
pytest containment tests.

---

## Post-PR-8 audit reconciliation

The post-PR-8 drift audit (`_post-pr8-drift-audit.md`) assigned these items to
this PR. They are NOT new tasks layered on top — they are corrections that
must be applied to the task descriptions below before implementation starts.

1. **Unfreeze `WorkerContext`.** Current code has
   `model_config = {"frozen": True}` on `WorkerContext(BaseModel)`. The RFC
   (`03-runtime.md` lines 299–313, 457–501) specifies a NON-frozen `BaseModel`
   with `PrivateAttr` fields `_task_mgmt`, `_task_inspect`, `_resource_repo`,
   plus a `_for_job` classmethod that injects services via
   `object.__setattr__`. Task 2's `WorkerContext` facade must first remove the
   `frozen` config and add the `PrivateAttr` declarations before the facade
   methods (`spawn_task`, `_assert_descendant`) can be added.
2. **Drop the `Task.created_by` assumption.** PR 7 added `created_by` to
   `Benchmark`, NOT to `Task`. If dynamic spawns need spawner identity,
   record it on the graph node or audit metadata. Audit any plan section
   that refers to `Task.created_by` and reroute.
3. **Add the missing graph + inspection methods.**
   `WorkflowGraphRepository.descendants_by_parent(...)` and
   `TaskInspectionService.descendant_ids(...)` do NOT exist yet — they need
   to be added as part of this PR (the SQL CTE in Task 2b is correct;
   just needs to be implemented rather than assumed-existing).
4. **Reconcile `add_subtask` signature drift.** Current
   `TaskManagementService.add_subtask(session, command: AddSubtaskCommand)`
   uses a command-object pattern. Task 3 must either extend the command to
   carry a full `Task` instance OR add a thin wrapper on `WorkerContext`
   that builds the command from `(task, depends_on)` and calls the service.
   Pick one and update Task 3 accordingly.
5. **Create `SpawnedTaskHandle` and `ContainmentViolation` as part of this PR.**
   Task 1 already covers `SpawnedTaskHandle`; ensure `ContainmentViolation`
   is added to `ergon_core/api/errors.py` (Task 2 Step 3's containment check
   raises it).

---

## Files

**Modify:**

```text
ergon_core/ergon_core/api/worker/context.py
ergon_core/ergon_core/api/worker/results.py
ergon_core/ergon_core/core/application/tasks/management.py
ergon_core/ergon_core/core/application/tasks/inspection.py
ergon_core/ergon_core/core/application/graph/repository.py
ergon_core/tests/unit/runtime/test_dynamic_task_evaluation_mapping.py
ergon_core/tests/unit/runtime/test_worker_context_containment.py
```

## Current State

Dynamic graph nodes exist, but runtime identity still mixes `node_id` and
`definition_task_id`. `WorkerContext` is mostly identity fields and does not
own the curated facade.

## Target State For This PR

```python
handle = await context.spawn_task(
    Task(
        task_slug="child",
        instance_key="sample-1",
        description="Research one child question.",
        worker=child_worker,
        sandbox=child_sandbox,
        evaluators=(),
    )
)
```

inserts:

```python
RunGraphNode(
    run_id=context.run_id,
    task_id=new_task_id,
    parent_task_id=context.task_id,
    task_json=task.model_dump(mode="json"),
    is_dynamic=True,
)
```

In the current schema this maps to `id=new_task_id` and
`parent_node_id=context.node_id`; PR 11 renames columns.

## Task 1: Add Spawned Handle

**Files:**

- Modify: `ergon_core/ergon_core/api/worker/results.py`

- [ ] **Step 1: Add model**

```python
class SpawnedTaskHandle(BaseModel):
    model_config = {"frozen": True}

    task_id: UUID

    async def wait(self) -> None:
        raise NotImplementedError("await_completion is deferred in v2")
```

Export it from `api/worker/__init__.py` and `api/__init__.py`.

## Task 2: Add WorkerContext Facade

**Files:**

- Modify: `ergon_core/ergon_core/api/worker/context.py`

- [ ] **Step 1: Add private services and constructor**

```python
class WorkerContext(BaseModel):
    run_id: UUID
    task_id: UUID
    execution_id: UUID
    definition_id: UUID
    node_id: UUID | None = None
    _task_mgmt: TaskManagementService = PrivateAttr()
    _task_inspect: TaskInspectionService = PrivateAttr()

    @classmethod
    def _for_job(cls, *, run_id, task_id, execution_id, definition_id, node_id, task_mgmt, task_inspect, resource_repo):
        instance = cls(run_id=run_id, task_id=task_id, execution_id=execution_id, definition_id=definition_id, node_id=node_id)
        object.__setattr__(instance, "_task_mgmt", task_mgmt)
        object.__setattr__(instance, "_task_inspect", task_inspect)
        object.__setattr__(instance, "_resource_repo", resource_repo)
        return instance
```

- [ ] **Step 2: Add containment exception**

In `ergon_core/ergon_core/api/errors.py` add:

```python
class ContainmentViolation(RuntimeError):
    """Raised when a worker tries to act on a task it does not own."""

    def __init__(self, *, parent_task_id: UUID, target_task_id: UUID) -> None:
        super().__init__(
            f"Task {target_task_id} is not a descendant of {parent_task_id}; "
            "WorkerContext can only mutate tasks it spawned or their descendants."
        )
        self.parent_task_id = parent_task_id
        self.target_task_id = target_task_id
```

Export it from `ergon_core.api`.

- [ ] **Step 3: Add facade methods**

In `WorkerContext`:

```python
async def spawn_task(
    self,
    task: Task,
    *,
    depends_on: tuple[UUID, ...] = (),
) -> SpawnedTaskHandle:
    return await self._task_mgmt.add_subtask(
        run_id=self.run_id,
        parent_task_id=self.task_id,
        task=task,
        depends_on=depends_on,
    )

async def cancel_task(self, task_id: UUID, *, reason: str = "") -> None:
    await self._assert_descendant(task_id)
    await self._task_mgmt.cancel_task(
        run_id=self.run_id,
        task_id=task_id,
        reason=reason,
    )

async def refine_task(self, task_id: UUID, *, description: str) -> None:
    await self._assert_descendant(task_id)
    await self._task_mgmt.refine_task(
        run_id=self.run_id,
        task_id=task_id,
        description=description,
    )

async def restart_task(self, task_id: UUID) -> SpawnedTaskHandle:
    await self._assert_descendant(task_id)
    return await self._task_mgmt.restart_task(
        run_id=self.run_id,
        task_id=task_id,
    )

async def subtasks(self) -> tuple[Task, ...]:
    return await self._task_inspect.children(
        run_id=self.run_id,
        parent_task_id=self.task_id,
    )

async def descendants(self) -> tuple[Task, ...]:
    return await self._task_inspect.descendants(
        run_id=self.run_id,
        root_task_id=self.task_id,
    )

async def get_task(self, task_id: UUID) -> Task:
    await self._assert_descendant(task_id)
    return await self._task_inspect.get(
        run_id=self.run_id,
        task_id=task_id,
    )

async def _assert_descendant(self, task_id: UUID) -> None:
    """Raise ContainmentViolation if task_id is not self.task_id or a descendant."""

    if task_id == self.task_id:
        return
    descendant_ids = await self._task_inspect.descendant_ids(
        run_id=self.run_id,
        root_task_id=self.task_id,
    )
    if task_id not in descendant_ids:
        raise ContainmentViolation(
            parent_task_id=self.task_id,
            target_task_id=task_id,
        )
```

The implementation deliberately re-reads descendants on every call rather
than caching them — `TaskInspectionService.descendant_ids` already memoizes
within a single Inngest step and a worker that spawns mid-step needs the
fresh set. `_assert_descendant` lives on `WorkerContext`, not on the service,
because containment is a facade-level rule.

## Task 2b: Add `descendant_ids` To Inspection Service

**Files:**

- Modify: `ergon_core/ergon_core/core/application/tasks/inspection.py`

- [ ] **Step 1: Add lookup**

```python
async def descendant_ids(
    self,
    *,
    run_id: UUID,
    root_task_id: UUID,
) -> frozenset[UUID]:
    """Return all task_ids reachable as children/grandchildren of root_task_id."""

    async with self._session() as session:
        rows = await self._graph_repo.descendants_by_parent(
            session,
            run_id=run_id,
            root_task_id=root_task_id,
        )
    return frozenset(row.task_id for row in rows)
```

Add the supporting `WorkflowGraphRepository.descendants_by_parent`. The
CTE is recursive on `parent_node_id` during the transition and renames to
`parent_task_id` after PR 11. Both SQLite and Postgres accept the
`WITH RECURSIVE` form below.

```python
from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import text

from ergon_core.core.persistence.graph.models import RunGraphNode


class WorkflowGraphRepository:
    ...

    async def descendants_by_parent(
        self,
        session,
        *,
        run_id: UUID,
        root_task_id: UUID,
    ) -> Sequence[RunGraphNode]:
        """Return all RunGraphNode rows transitively reachable from
        root_task_id via parent_node_id, NOT including the root itself.
        """

        # During the transition the canonical identity column is `id`
        # (with `parent_node_id` pointing at parent.id). PR 11 renames to
        # `task_id` / `parent_task_id`; update the column references in
        # the same commit that does the rename.
        cte_sql = text(
            """
            WITH RECURSIVE descendants AS (
                SELECT id, parent_node_id, run_id
                FROM run_graph_nodes
                WHERE run_id = :run_id
                  AND parent_node_id = :root_task_id

                UNION ALL

                SELECT child.id, child.parent_node_id, child.run_id
                FROM run_graph_nodes AS child
                JOIN descendants ON child.parent_node_id = descendants.id
                WHERE child.run_id = :run_id
            )
            SELECT id FROM descendants
            """
        )
        result = session.exec(
            cte_sql.bindparams(run_id=str(run_id), root_task_id=str(root_task_id))
        ).all()
        descendant_ids = [row[0] for row in result]
        if not descendant_ids:
            return ()

        return session.exec(
            select(RunGraphNode).where(RunGraphNode.id.in_(descendant_ids))
        ).all()
```

SQLite needs the foreign-key parameters as strings (`str(run_id)`) because
the `sqlite3` driver does not auto-cast `UUID`. Postgres accepts either.

The recursion bound is implicit (the run graph is a DAG built only by
`spawn_task`; cycles are prevented at insertion time by
`add_node`'s parent-resolution check). If a stress test later needs an
explicit depth cap, add `WHERE level < :max_depth` to the recursive arm.

## Task 3: Management Service Inserts Dynamic Task JSON

**Files:**

- Modify: `ergon_core/ergon_core/core/application/tasks/management.py`

- [ ] **Step 1: Add object-bound overload**

```python
async def add_subtask(
    self,
    *,
    run_id: UUID,
    parent_task_id: UUID,
    task: Task,
    depends_on: tuple[UUID, ...] = (),
) -> SpawnedTaskHandle:
    new_task_id = uuid4()
    async with self._session() as session:
        parent = self._graph_repo.node(session, run_id=run_id, task_id=parent_task_id)
        node = await self._graph_repo.add_node(
            session,
            run_id,
            task_slug=task.task_slug,
            instance_key=task.instance_key,
            description=task.description,
            status=graph_status.PENDING,
            parent_node_id=parent.node_id,
            level=parent.level + 1,
            task_json=task.model_dump(mode="json"),
            is_dynamic=True,
            meta=MutationMeta(actor="worker-context", reason="spawn_task"),
        )
        for dep in depends_on:
            dep_node = self._graph_repo.node(session, run_id=run_id, task_id=dep)
            await self._graph_repo.add_edge(
                session,
                run_id,
                source_node_id=dep_node.node_id,
                target_node_id=node.id,
                status=graph_status.PENDING,
                meta=MutationMeta(actor="worker-context", reason="spawn dependency"),
            )
        session.commit()
    return SpawnedTaskHandle(task_id=new_task_id)
```

Adjust field names to the actual DTO returned by `add_node`; the invariant
is that no definition table is written.

## Task 4: Tests

**Files:**

- Create: `ergon_core/tests/unit/runtime/test_worker_context_containment.py`
- Modify: `ergon_core/tests/unit/runtime/test_dynamic_task_evaluation_mapping.py`

- [ ] **Step 1: Dynamic spawn writes no definition row**

```python
from sqlmodel import select, func

from ergon_core.core.persistence.definitions.models import ExperimentDefinitionTask
from ergon_core.core.persistence.graph.models import RunGraphNode
from ergon_core.api.benchmark.task import Task
from tests.unit.runtime._test_workers import EchoWorker, EchoSandbox


@pytest.mark.asyncio
async def test_spawn_task_does_not_write_definition_task_row(
    session,
    worker_context_factory,
    run_graph_factory,
):
    graph = run_graph_factory(nodes=[("root", None)])
    context = worker_context_factory(
        run_id=graph.run_id,
        task_id=graph.task_id("root"),
    )

    before = session.exec(
        select(func.count()).select_from(ExperimentDefinitionTask)
    ).one()

    handle = await context.spawn_task(
        Task(
            task_slug="child",
            instance_key="sample-1",
            description="spawned child",
            worker=EchoWorker(name="echo", model=None),
            sandbox=EchoSandbox(),
            evaluators=(),
        )
    )

    after = session.exec(
        select(func.count()).select_from(ExperimentDefinitionTask)
    ).one()
    assert after == before, "dynamic spawn must not create a definition row"

    # Spawned node exists in run_graph_nodes with is_dynamic=true.
    row = session.exec(
        select(RunGraphNode).where(RunGraphNode.id == handle.task_id)
    ).one()
    assert row.is_dynamic is True
    assert row.task_json["task_slug"] == "child"
```

- [ ] **Step 2: Same runtime path loads spawned tasks**

```python
@pytest.mark.asyncio
async def test_spawned_task_inflates_through_graph_repo_node(
    session,
    worker_context_factory,
    run_graph_factory,
    graph_repo,
):
    graph = run_graph_factory(nodes=[("root", None)])
    context = worker_context_factory(
        run_id=graph.run_id,
        task_id=graph.task_id("root"),
    )

    handle = await context.spawn_task(
        Task(
            task_slug="child",
            instance_key="sample-1",
            description="spawned child",
            worker=EchoWorker(name="echo", model=None),
            sandbox=EchoSandbox(),
            evaluators=(),
        )
    )

    view = graph_repo.node(
        session,
        run_id=graph.run_id,
        task_id=handle.task_id,
    )

    assert view.task.task_slug == "child"
    assert view.task.task_id == handle.task_id
    assert view.is_dynamic is True
    # Object-bound reconstruction works for spawned snapshots too:
    assert isinstance(view.task.worker, EchoWorker)
    assert isinstance(view.task.sandbox, EchoSandbox)
```

- [ ] **Step 3: Containment**

```python
@pytest.mark.asyncio
async def test_worker_context_cancel_raises_on_non_descendant(
    worker_context_factory,
    run_graph_factory,
):
    graph = run_graph_factory(
        nodes=[
            ("root", None),
            ("sibling", None),  # peer of root, NOT a child
            ("child", "root"),
        ]
    )
    context = worker_context_factory(
        run_id=graph.run_id,
        task_id=graph.task_id("root"),
    )
    # Spawned descendants are fine:
    await context.cancel_task(graph.task_id("child"))

    # A sibling task is outside the containment boundary:
    with pytest.raises(ContainmentViolation) as excinfo:
        await context.cancel_task(graph.task_id("sibling"))

    assert excinfo.value.parent_task_id == graph.task_id("root")
    assert excinfo.value.target_task_id == graph.task_id("sibling")
```

The `run_graph_factory` fixture is the same one used by the dynamic-spawn
test in Step 2; if it does not yet support a `nodes=[(slug, parent_slug)]`
form, extend it in the same commit.

- [ ] **Step 4: Run tests**

```bash
uv run pytest ergon_core/tests/unit/runtime/test_dynamic_task_evaluation_mapping.py \
  ergon_core/tests/unit/runtime/test_worker_context_containment.py -q
```

## Task 5: Flip XFails Landed By This PR

**Files:**

- Modify: `ergon_core/tests/unit/architecture/test_v2_final_state_ledger.py`
- Modify: `ergon_core/tests/unit/architecture/test_dead_path_audit.py`
- Modify: `ergon_core/tests/unit/runtime/test_walkthrough_smoketest.py`
- Modify: `ergon_core/tests/unit/runtime/test_identity_invariants.py`

PR 9 closes Δ.3 — dynamic subtasks are graph-native. Four ledger entries
flip:

- [ ] **Step 1: Remove `materialize_dynamic_subtask_definition_is_gone` from `_XFAIL_BY_NAME`**

In `test_v2_final_state_ledger.py`, delete:

```python
"materialize_dynamic_subtask_definition_is_gone": "PR 9 makes dynamic subtasks graph-native",
```

- [ ] **Step 2: Remove the dead-path entry**

In `test_dead_path_audit.py`, delete:

```python
"materialize_dynamic_subtask_definition": "PR 9: graph-native dynamic spawn",
```

- [ ] **Step 3: Flip the smoketest and identity cases**

In `test_walkthrough_smoketest.py`, remove the xfail decorator on
`test_dynamic_spawn_writes_only_to_run_graph_nodes` and implement the
real body: drive `WorkerContext.spawn_task` from a parent task context,
then assert the spawned `task_id` has zero rows in
`experiment_definition_tasks` and exactly one row in `run_graph_nodes`
with `is_dynamic=True`.

In `test_identity_invariants.py`, remove the xfail on
`test_dynamic_task_id_has_no_definition_row` and implement the real body.

- [ ] **Step 4: Run the ledgers**

```bash
uv run pytest \
  ergon_core/tests/unit/architecture/test_v2_final_state_ledger.py \
  ergon_core/tests/unit/architecture/test_dead_path_audit.py \
  ergon_core/tests/unit/runtime/test_walkthrough_smoketest.py \
  ergon_core/tests/unit/runtime/test_identity_invariants.py -q
```

Expected: four more cases PASS; PR 11 entries still XFAIL.

## PR Ledger

Invariant landed: dynamic tasks are graph-native.

Bridge code introduced: `node_id` remains in WorkerContext during schema
transition.

Old path still intentionally alive: runtime identity fields until PR 11.

Deletion gate: PR 11 removes `node_id` from context and graph DTOs.

Tests added or updated: dynamic spawn and containment tests.

Modules owned by this PR: WorkerContext and task management.
