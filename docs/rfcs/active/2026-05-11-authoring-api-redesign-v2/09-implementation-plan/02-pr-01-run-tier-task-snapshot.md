# PR 1 — Run-Tier Task Snapshot Foundation

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` or
> `superpowers:executing-plans` to implement this plan task-by-task.

**Goal:** Make each `run_graph_nodes` row capable of carrying a full task
snapshot while old runtime readers continue to work.

**Architecture:** Add `task_json` and `is_dynamic` to run graph nodes. During
run preparation, copy definition task data into `task_json`. Do not remove
`definition_task_id`, `id`, `task_slug`, `description`, or
`assigned_worker_slug` in this PR.

**Tech Stack:** SQLModel, Alembic additive migration, pytest runtime tests.

---

## Files

**Modify:**

```text
ergon_core/ergon_core/core/persistence/graph/models.py
ergon_core/ergon_core/core/application/graph/repository.py
ergon_core/ergon_core/core/application/workflows/service.py
ergon_core/ergon_core/core/application/jobs/start_workflow.py
ergon_core/tests/unit/runtime/test_graph_worker_identity.py
ergon_core/tests/unit/runtime/test_dynamic_task_evaluation_mapping.py
```

**Create:**

```text
ergon_core/migrations/versions/<revision>_add_run_graph_task_json.py
ergon_core/tests/unit/runtime/test_run_graph_task_snapshot.py
ergon_core/tests/unit/runtime/test_walkthrough_smoketest.py
ergon_core/tests/unit/runtime/test_identity_invariants.py
```

## Current State

`RunGraphNode` stores dispatch fields:

```python
id: UUID
run_id: UUID
definition_task_id: UUID | None
instance_key: str
task_slug: str
description: str
assigned_worker_slug: str | None
```

Static runtime reconstruction still follows `definition_task_id` back to
`ExperimentDefinitionTask`. Dynamic nodes have no definition row and use the
graph-native path.

## Target State For This PR

`RunGraphNode` additionally stores:

```python
task_json: dict
is_dynamic: bool
```

Static nodes receive a snapshot copied from definition tables. Dynamic nodes
can receive a snapshot at creation time. Existing runtime code keeps reading
old fields until later PRs flip it.

## Task 1: Add Schema Fields

**Files:**

- Modify: `ergon_core/ergon_core/core/persistence/graph/models.py`
- Create: `ergon_core/migrations/versions/<revision>_add_run_graph_task_json.py`

- [x] **Step 1: Update `RunGraphNode`**

Add imports:

```python
from sqlalchemy import Boolean
```

Add fields after `description`:

```python
    task_json: dict = Field(
        default_factory=dict,
        sa_column=Column(JSON),
        description=(
            "Run-tier snapshot of the authored Task. Static nodes copy this "
            "from experiment_definition_tasks at prepare-run time; dynamic "
            "nodes write it directly at spawn time."
        ),
    )
    is_dynamic: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, default=False),
        description="True when this node was spawned during a run.",
    )
```

Keep `definition_task_id` unchanged.

- [x] **Step 2: Add additive migration**

Create a migration that runs:

```python
def upgrade() -> None:
    op.add_column(
        "run_graph_nodes",
        sa.Column("task_json", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.add_column(
        "run_graph_nodes",
        sa.Column("is_dynamic", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index(
        "ix_run_graph_nodes_run_dynamic",
        "run_graph_nodes",
        ["run_id", "is_dynamic"],
    )


def downgrade() -> None:
    op.drop_index("ix_run_graph_nodes_run_dynamic", table_name="run_graph_nodes")
    op.drop_column("run_graph_nodes", "is_dynamic")
    op.drop_column("run_graph_nodes", "task_json")
```

- [x] **Step 3: Run model import smoke**

Run:

```bash
uv run python -c "from ergon_core.core.persistence.graph.models import RunGraphNode; print(RunGraphNode.model_fields['task_json'].default_factory)"
```

Expected: prints a callable/default factory reference and exits 0.

## Task 2: Copy Definition Task JSON During Prepare

**Files:**

- Modify: `ergon_core/ergon_core/core/application/graph/repository.py`

- [x] **Step 1: Add helper near `_node_snapshot` helpers**

```python
def _definition_task_snapshot(
    task: ExperimentDefinitionTask,
    *,
    instance_key: str,
    assigned_worker_slug: str | None,
) -> dict:
    return {
        "_type": "ergon_core.api.benchmark.task:TaskSpec",
        "task_slug": task.task_slug,
        "instance_key": instance_key,
        "description": task.description,
        "parent_task_slug": None,
        "dependency_task_slugs": (),
        "evaluator_binding_keys": (),
        "task_payload": task.task_payload_json,
        "_legacy": {
            "assigned_worker_slug": assigned_worker_slug,
            "definition_task_id": str(task.id),
        },
    }
```

This is a bridge snapshot, not the final v2 `Task` JSON. PR 5 replaces the
payload shape once object-bound tasks exist.

- [x] **Step 2: Populate `task_json` when creating static nodes**

Replace the `RunGraphNode(...)` creation inside `initialize_from_definition`
with the same fields plus:

```python
task_json=_definition_task_snapshot(
    task,
    instance_key=instance_key_by_id[task.instance_id],
    assigned_worker_slug=worker_by_task.get(task.id),
),
is_dynamic=False,
```

- [x] **Step 3: Populate `task_json` in `add_node`**

Extend `add_node` signature:

```python
        task_json: dict | None = None,
        is_dynamic: bool = True,
```

Pass into `RunGraphNode(...)`:

```python
task_json=task_json or {},
is_dynamic=is_dynamic,
```

Existing callers of `add_node` become dynamic by default. If a static caller
exists outside `initialize_from_definition`, pass `is_dynamic=False`
explicitly.

## Task 3: Add Focused Tests

**Files:**

- Create: `ergon_core/tests/unit/runtime/test_run_graph_task_snapshot.py`

- [x] **Step 1: Write static-copy test**

```python
def test_initialize_from_definition_copies_task_json(session, definition_factory):
    definition = definition_factory(task_slug="solve", payload={"problem": "p"})
    repo = WorkflowGraphRepository()

    graph = repo.initialize_from_definition(
        session,
        run_id=uuid4(),
        definition_id=definition.definition_id,
        initial_node_status="pending",
        initial_edge_status="pending",
        task_payload_model=EmptyTaskPayload,
        meta=MutationMeta(actor="test", reason="snapshot"),
    )

    row = session.get(RunGraphNode, graph.nodes[0].id)
    assert row is not None
    assert row.task_json["task_slug"] == "solve"
    assert row.task_json["task_payload"] == {"problem": "p"}
    assert row.is_dynamic is False
```

- [x] **Step 2: Write dynamic insert test**

```python
@pytest.mark.asyncio
async def test_add_node_can_write_dynamic_task_json(session):
    repo = WorkflowGraphRepository()
    run_id = uuid4()
    payload = {
        "_type": "ergon_core.api.benchmark.task:Task",
        "task_slug": "child",
        "description": "child task",
    }

    node = await repo.add_node(
        session,
        run_id,
        task_slug="child",
        instance_key="sample-1",
        description="child task",
        status="pending",
        task_json=payload,
        is_dynamic=True,
        meta=MutationMeta(actor="test", reason="dynamic"),
    )

    row = session.get(RunGraphNode, node.id)
    assert row is not None
    assert row.task_json == payload
    assert row.is_dynamic is True
```

- [x] **Step 3: Run focused tests**

```bash
uv run pytest ergon_core/tests/unit/runtime/test_run_graph_task_snapshot.py -q
```

## Task 4: Add Walkthrough Smoketest Skeleton

**Files:**

- Create: `ergon_core/tests/unit/runtime/test_walkthrough_smoketest.py`

The walkthrough smoketest is the **observable-effect** counterpart to the
xfail ledgers from PR 0. Each test drives a public entry point (e.g.
`persist_definition`, `prepare_run`, `worker_execute`) and asserts the
database / event-bus state the spec requires. PR 1 lands the skeleton
plus one passing case (the PR 1 invariant). Every other case is xfail
with strict=True until its landing PR flips it green.

These are explicitly **not** call-graph mock tests — they observe outcomes
(rows in tables, events on the bus), not call topology. The walkthrough
integration test in PR 12 is the heavier, multi-variant version of the
same pattern; this skeleton is the unit-level seed.

- [x] **Step 1: Write the smoketest skeleton**

```python
"""Observable-effect smoketests for the v2 happy path.

Each test drives a public entry point and asserts database / event state
that the spec requires. NOT call-graph tests — outcomes only. See
07-test-strategy.md § "Why effect-based smoketests, not call-graph mocks".

Tests for invariants that have not landed are xfail(strict=True) with the
landing PR in the reason. Removing the decorator is the landing-PR signal.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


async def test_prepare_run_populates_task_json_for_every_node(
    session, persisted_definition
):
    """PR 1 invariant — must be GREEN after PR 1 lands.

    Every run_graph_nodes row produced by prepare_run carries a non-empty
    task_json snapshot.
    """

    from sqlmodel import select

    from ergon_core.core.application.workflows.service import prepare_run
    from ergon_core.core.persistence.graph.models import RunGraphNode

    run_id = await prepare_run(session, definition_id=persisted_definition.id)
    rows = session.exec(
        select(RunGraphNode).where(RunGraphNode.run_id == run_id)
    ).all()

    assert rows, "prepare_run produced no nodes"
    assert all(row.task_json for row in rows), (
        "every node must carry a self-contained task snapshot"
    )
    assert all(row.task_json.get("task_slug") for row in rows)


@pytest.mark.xfail(
    reason="PR 7: persist_definition collapses ExperimentRecord onto definitions",
    strict=True,
)
async def test_persist_definition_writes_only_intended_tables(
    session, sample_experiment
):
    """PR 7 invariant: persist_definition writes experiment_definitions
    plus experiment_definition_tasks. No write to ExperimentRecord, no
    write to saved_specs."""

    from sqlmodel import select

    from ergon_core.core.application.experiments.definition_writer import (
        persist_definition,
    )
    from ergon_core.core.persistence.definitions.models import (
        ExperimentDefinition,
        ExperimentDefinitionTask,
    )

    persist_definition(session, sample_experiment)

    defs = session.exec(select(ExperimentDefinition)).all()
    tasks = session.exec(select(ExperimentDefinitionTask)).all()
    assert len(defs) == 1
    assert len(tasks) == len(sample_experiment.benchmark.tasks)


@pytest.mark.xfail(
    reason="PR 3: worker_execute reads task from run_graph_nodes only",
    strict=True,
)
async def test_worker_execute_reads_task_from_run_tier_only(
    session, prepared_run, inngest_driver
):
    """PR 3 invariant: worker_execute touches no definition-tier table.

    Observed by spying the session for query targets — not by mocking
    call paths. The fixture `prepared_run` is added in PR 3 alongside
    this assertion turning green.
    """

    pytest.fail("requires PR 3's worker-execute cutover and prepared_run fixture")


@pytest.mark.xfail(
    reason="PR 4: synchronous fanout via ctx.step.invoke",
    strict=True,
)
async def test_worker_execute_emits_one_evaluate_invocation_per_evaluator(
    inngest_driver, run_with_two_evaluators
):
    """PR 4 invariant: synchronous fanout via ctx.step.invoke."""

    pytest.fail("requires PR 4's fanout shape")


@pytest.mark.xfail(
    reason="PR 4: TaskEvaluateRequest is the thin id-only payload",
    strict=True,
)
async def test_evaluate_task_run_payload_is_id_only(
    inngest_driver, run_with_one_evaluator
):
    """PR 4 invariant: TaskEvaluateRequest has exactly four fields:
    run_id, task_id, execution_id, evaluator_index."""

    pytest.fail("requires PR 4's TaskEvaluateRequest")


@pytest.mark.xfail(
    reason="PR 4: orchestrator try/finally bounds sandbox lifetime through gather",
    strict=True,
)
async def test_sandbox_release_happens_after_all_evaluators_complete(
    inngest_driver, run_with_two_evaluators
):
    """Δ.5: orchestrator's try/finally bounds sandbox lifetime through gather."""

    pytest.fail("requires PR 4's lifecycle ownership")


@pytest.mark.xfail(
    reason="PR 9: dynamic subtasks write only to run_graph_nodes",
    strict=True,
)
async def test_dynamic_spawn_writes_only_to_run_graph_nodes(
    session, running_run, parent_task_context
):
    """Δ.3 / PR 9 invariant: dynamic subtasks are graph-native."""

    pytest.fail("requires PR 9's graph-native dynamic spawn")


@pytest.mark.xfail(
    reason="PR 11: full v2 lifecycle — every acquire has a release",
    strict=True,
)
async def test_run_completion_releases_every_acquired_sandbox(
    inngest_driver, run_with_three_tasks
):
    """CLAUDE.md guardrail: every sandbox acquire has a release."""

    pytest.fail("requires the full v2 lifecycle shape")
```

The fixtures `persisted_definition`, `sample_experiment`, `prepared_run`,
`inngest_driver`, `run_with_two_evaluators`, etc. are introduced by the
PR that flips the corresponding test green. PR 1 only needs
`persisted_definition` and `session`; the rest are added by their
landing PR.

- [x] **Step 2: Add the minimal PR 1 fixtures**

In `ergon_core/tests/unit/runtime/conftest.py` (extend if it exists):

```python
import pytest
from sqlmodel import Session, SQLModel, create_engine

from ergon_core.core.application.experiments.definition_writer import (
    persist_definition,
)


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture()
def persisted_definition(session, sample_experiment):
    return persist_definition(session, sample_experiment)
```

The `sample_experiment` fixture lives where the existing benchmark test
fixtures live; reuse the simplest in-tree benchmark that builds a
non-empty graph.

- [x] **Step 3: Run the smoketest**

```bash
uv run pytest ergon_core/tests/unit/runtime/test_walkthrough_smoketest.py -q
```

Expected on PR 1: one PASS
(`test_prepare_run_populates_task_json_for_every_node`), seven XFAIL,
zero FAIL, zero XPASS.

## Task 5: Add Identity Invariants Skeleton

**Files:**

- Create: `ergon_core/tests/unit/runtime/test_identity_invariants.py`

Tests the identity-flow invariants from
[`02-persistence-layer.md`](../02-persistence-layer.md) §2: `task_id` is
born once and flows unchanged, `(run_id, task_id)` is the canonical row
key, `execution_id` is the per-attempt id, sandbox identity is preserved
across the worker → evaluate Inngest boundary.

The PR 1 invariant (task_id flows from definition tasks into
`run_graph_nodes`) is green; later invariants xfail until their landing
PR.

- [x] **Step 1: Write the skeleton**

```python
"""Identity-flow invariants from 02-persistence-layer.md §2.

task_id is born once and flows unchanged. (run_id, task_id) is the
canonical row key. execution_id is the per-attempt id. Sandbox identity
is preserved across the worker → evaluate Inngest boundary.

These are observable-effect tests, not call-graph tests.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


async def test_task_id_is_preserved_from_definition_to_run_tier(
    session, persisted_definition
):
    """PR 1 invariant: the same UUID flows from
    experiment_definition_tasks → run_graph_nodes.task_id (via
    definition_task_id during the transition; PR 11 collapses to task_id).
    """

    from sqlmodel import select

    from ergon_core.core.application.workflows.service import prepare_run
    from ergon_core.core.persistence.definitions.models import (
        ExperimentDefinitionTask,
    )
    from ergon_core.core.persistence.graph.models import RunGraphNode

    defn_tasks = session.exec(
        select(ExperimentDefinitionTask).where(
            ExperimentDefinitionTask.experiment_definition_id
            == persisted_definition.id
        )
    ).all()
    defn_task_ids = {t.id for t in defn_tasks}

    run_id = await prepare_run(session, definition_id=persisted_definition.id)
    nodes = session.exec(
        select(RunGraphNode).where(RunGraphNode.run_id == run_id)
    ).all()

    # During the transition, identity lives in either `id` (run-tier minted)
    # or `definition_task_id` (copied from definition). PR 11 collapses to
    # `task_id` only.
    node_identity = {(n.definition_task_id or n.id) for n in nodes}
    assert defn_task_ids == node_identity, (
        f"task_id did not survive prepare_run: definition={defn_task_ids}, "
        f"run-tier={node_identity}"
    )


@pytest.mark.xfail(
    reason="PR 2: graph_repo.node binds task._task_id from the run-tier row",
    strict=True,
)
async def test_task_id_propagates_into_runtime_task_instance(
    session, persisted_definition
):
    """PR 2 invariant: Task.from_definition binds _task_id; reading
    `task.task_id` on the inflated instance returns the same UUID the
    definition row had."""

    pytest.fail("requires PR 2's typed run-node boundary")


@pytest.mark.xfail(
    reason="PR 4: orchestrator stamps sandbox_id on run_task_executions",
    strict=True,
)
async def test_sandbox_identity_is_preserved_across_worker_to_evaluate_boundary(
    session, inngest_driver, run_with_one_evaluator
):
    """Δ.5: the sandbox acquired in worker_execute is the one each
    evaluate_task_run invocation attaches to via sandbox_id."""

    pytest.fail("requires PR 4's persisted sandbox_id contract")


@pytest.mark.xfail(
    reason="PR 4: execution_id flows through TaskEvaluateRequest payload",
    strict=True,
)
async def test_execution_id_is_unique_per_attempt_and_shared_across_evaluators(
    session, inngest_driver, run_with_two_evaluators
):
    """Two evaluator invocations for the same execution share execution_id;
    a retry mints a new one."""

    pytest.fail("requires PR 4's TaskEvaluateRequest")


@pytest.mark.xfail(
    reason="PR 9: dynamic task_id is fresh uuid4 with no definition row",
    strict=True,
)
async def test_dynamic_task_id_has_no_definition_row(
    session, running_run, parent_task_context
):
    """Δ.3: dynamic spawn writes only to run_graph_nodes."""

    pytest.fail("requires PR 9's graph-native spawn")
```

- [x] **Step 2: Run the identity tests**

```bash
uv run pytest ergon_core/tests/unit/runtime/test_identity_invariants.py -q
```

Expected: one PASS, four XFAIL.

- [x] **Step 3: Commit**

```bash
git add ergon_core/tests/unit/runtime/test_run_graph_task_snapshot.py \
        ergon_core/tests/unit/runtime/test_walkthrough_smoketest.py \
        ergon_core/tests/unit/runtime/test_identity_invariants.py \
        ergon_core/migrations/versions/*_add_run_graph_task_json.py \
        ergon_core/ergon_core/core/persistence/graph/models.py \
        ergon_core/ergon_core/core/application/graph/repository.py
git commit -m "feat: run-tier task snapshot + walkthrough/identity test skeletons"
```

## Task 6: Rename `telemetry/repositories.py` → `telemetry/repository.py`

**Files:**

- Move: `ergon_core/ergon_core/core/persistence/telemetry/repositories.py`
  → `ergon_core/ergon_core/core/persistence/telemetry/repository.py`
- Modify: every importer of `ergon_core.core.persistence.telemetry.repositories`
- Modify: `ergon_core/tests/unit/architecture/test_repository_layer_conventions.py`
  (remove the `TelemetryRepository` entry from `_KNOWN_VIOLATORS`)

PR 0.5's repository-layer-conventions guard xfails the
`test_repository_file_is_singular[TelemetryRepository]` case until this
rename lands. PR 1 is the natural home because no other PR is heavily
editing `telemetry/repositories.py` first — PR 4 touches it next.

- [x] **Step 1: Rename the file**

```bash
git mv ergon_core/ergon_core/core/persistence/telemetry/repositories.py \
       ergon_core/ergon_core/core/persistence/telemetry/repository.py
```

- [x] **Step 2: Update importers**

```bash
rg -l "from ergon_core\.core\.persistence\.telemetry\.repositories" \
   ergon_core ergon_builtins ergon_cli
```

Edit each hit to `... .telemetry.repository`. Same for any
`import ergon_core.core.persistence.telemetry.repositories as ...` form.

- [x] **Step 3: Remove the xfail entry**

In `test_repository_layer_conventions.py`, delete:

```python
("test_repository_file_is_singular", "TelemetryRepository"):
    "PR 1: rename telemetry/repositories.py -> telemetry/repository.py",
```

- [x] **Step 4: Run the guard**

```bash
uv run pytest ergon_core/tests/unit/architecture/test_repository_layer_conventions.py -q
```

Expected: the `TelemetryRepository` filename case now PASSes; no XPASS.

## PR Ledger

Invariant landed: run graph nodes carry self-contained task snapshots.

Bridge code introduced: bridge snapshot uses `TaskSpec`-shaped JSON.

Old path still intentionally alive: `definition_task_id` and definition-tier
runtime lookup.

Deletion gate: PR 11 deletes old runtime identity fields after PRs 2-10 flip
all consumers.

Tests added or updated: `test_run_graph_task_snapshot.py`,
`test_walkthrough_smoketest.py` (one passing, seven xfail),
`test_identity_invariants.py` (one passing, four xfail).

Modules owned by this PR: persistence and graph repository; observable-effect
smoketest skeletons that subsequent PRs will flip green.
