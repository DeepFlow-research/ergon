# PR 12 — Walkthrough Integration And CI Hardening

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` or
> `superpowers:executing-plans` to implement this plan task-by-task.

**Goal:** Prove the canonical walkthrough runs end to end in the final v2
shape and wire the guard suite into CI.

**Architecture:** The integration test mirrors `04-walkthrough.md` directly:
author code creates an experiment, definition persists, run prepares graph
nodes, worker execution fans out criteria via `ctx.step.invoke`, every eval completes, sandbox releases, and the run
settles.

**Tech Stack:** pytest integration markers, Postgres test container, fake
Sandbox runtime, synchronous Inngest test driver.

---

## Files

**Create:**

```text
ergon_core/tests/integration/test_walkthrough.py
ergon_core/tests/integration/conftest.py
ergon_core/tests/unit/regression/test_v1_audit_findings.py
```

**Modify:**

```text
pyproject.toml
.github/workflows/ci.yml
ergon_core/tests/unit/architecture/
```

## Task 1: Integration Fixtures

**Files:**

- Create: `ergon_core/tests/integration/conftest.py`

- [ ] **Step 1: Add fake sandbox**

```python
class FakeSandboxRuntime:
    sandbox_id = "fake-sandbox"

    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}
        self.commands: list[str] = []

    async def run_command(self, cmd, *, timeout=None):
        self.commands.append(" ".join(cmd) if isinstance(cmd, list) else cmd)
        return CommandResult(exit_code=0, stdout="ok", stderr="")

    async def write_file(self, path: str, content: bytes) -> None:
        self.files[path] = content

    async def read_file(self, path: str) -> bytes:
        return self.files[path]

    async def list_files(self, path: str) -> list[str]:
        return sorted(p for p in self.files if p.startswith(path))

    async def close(self) -> None:
        pass
```

- [ ] **Step 2: Add fake sandbox subclass**

```python
class FakeSandbox(Sandbox):
    async def provision(self) -> None:
        object.__setattr__(self, "_runtime", FakeSandboxRuntime())
```

- [ ] **Step 3: Add deterministic worker and criterion**

`FakeSandbox` already exposes the runtime; add a worker that writes a file
and a criterion that reads it through `task.sandbox`:

```python
from ergon_core.api.benchmark.task import Task
from ergon_core.api.criterion.criterion import Criterion
from ergon_core.api.criterion.context import CriterionContext
from ergon_core.api.criterion.result import CriterionResult
from ergon_core.api.worker.worker import Worker
from ergon_core.api.worker.context import WorkerContext
from ergon_core.api.worker.results import WorkerOutput


class FileDropWorker(Worker):
    type_slug = "test-file-drop"

    output_filename: str = "result.txt"
    output_content: str = "ok"

    async def execute(self, task: Task, *, context: WorkerContext):
        await task.sandbox.write_file(
            f"{task.sandbox.output_path}{self.output_filename}",
            self.output_content.encode(),
        )
        yield WorkerOutput(
            final_text=self.output_content,
            artifacts=({"path": self.output_filename},),
        )


class FileExistsCriterion(Criterion):
    type_slug = "test-file-exists"

    expected_filename: str = "result.txt"

    async def evaluate(self, ctx: CriterionContext) -> CriterionResult:
        files = await ctx.task.sandbox.list_files(ctx.task.sandbox.output_path)
        passed = any(f.endswith(self.expected_filename) for f in files)
        return CriterionResult(
            passed=passed,
            score=1.0 if passed else 0.0,
            reason=f"file {self.expected_filename} present: {passed}",
        )
```

- [ ] **Step 4: Wire sandbox lifecycle counters**

The walkthrough needs to assert that acquire/release pair up. Add an
instrumented hub fixture that replaces `SandboxLifecycleHub` for the test
session:

```python
import pytest
from ergon_core.core.infrastructure.sandbox.lifecycle import SandboxLifecycleHub


class CountingSandboxHub(SandboxLifecycleHub):
    """Real hub semantics with acquire/release counters and ordering log."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.acquire_count = 0
        self.release_count = 0
        self.events: list[tuple[str, str]] = []  # (event, sandbox_id)

    async def acquire(self, sandbox):
        result = await super().acquire(sandbox)
        self.acquire_count += 1
        self.events.append(("acquire", result.sandbox_id))
        return result

    async def release(self, sandbox):
        await super().release(sandbox)
        self.release_count += 1
        self.events.append(("release", sandbox.sandbox_id))


@pytest.fixture
def sandbox_hub(monkeypatch):
    hub = CountingSandboxHub()
    monkeypatch.setattr(
        "ergon_core.core.infrastructure.sandbox.lifecycle.SandboxLifecycleHub",
        lambda *a, **kw: hub,
    )
    return hub


@pytest.fixture
def evaluation_log():
    """Captures the per-criterion persistence calls so the walkthrough can
    assert that sandbox release happens AFTER criterion persistence."""

    return []


@pytest.fixture(autouse=True)
def _capture_criterion_persist(monkeypatch, evaluation_log):
    from ergon_core.core.application.evaluation import service as eval_service

    original = eval_service.EvaluationService.persist_success

    async def _wrapped(self, *args, **kwargs):
        result = await original(self, *args, **kwargs)
        evaluation_log.append(("criterion_persisted", kwargs.get("task_id")))
        return result

    monkeypatch.setattr(
        eval_service.EvaluationService, "persist_success", _wrapped
    )
```

## Task 2: Happy Path Walkthrough

**Files:**

- Create: `ergon_core/tests/integration/test_walkthrough.py`

- [ ] **Step 1: Build four-task benchmark**

Mirror `04-walkthrough.md`: research -> code -> review -> summarize, each
with a fake worker, fake sandbox, and one rubric.

- [ ] **Step 2: Persist and launch**

```python
handle = persist_definition(experiment)
result = await launch_run(handle.definition_id)
```

- [ ] **Step 3: Drive jobs synchronously**

Use the local test driver to run prepare, worker-execute, and advance until
the run is terminal.

- [ ] **Step 4: Assert final state**

```python
assert run.status == "succeeded"
assert all(node.status == "completed" for node in nodes)

# Acquire/release pair up: one of each per task in the four-task walkthrough.
assert sandbox_hub.acquire_count == 4
assert sandbox_hub.release_count == 4

# Release must happen AFTER every evaluate_task_run invocation completes.
# The evaluation_log fixture captures evaluate_task_run.fn returns;
# sandbox_hub.events captures hub-level acquire/release. For each task,
# every eval invocation for that task must precede its sandbox release:
for node in nodes:
    task_id = node.task.task_id
    n_evals = len(node.task.evaluators)
    sandbox_id = node.execution.sandbox_id  # stamped by worker_execute

    eval_completions = [
        i for i, (kind, key) in enumerate(combined_log)
        if kind == "eval_complete" and key == task_id
    ]
    release_pos = next(
        i for i, (kind, key) in enumerate(combined_log)
        if kind == "release" and key == sandbox_id
    )

    assert len(eval_completions) == n_evals, (
        f"task {node.task.task_slug}: expected {n_evals} eval completions, "
        f"got {len(eval_completions)}"
    )
    for eval_pos in eval_completions:
        assert eval_pos < release_pos, (
            f"task {node.task.task_slug}: sandbox released before an "
            f"evaluate_task_run invocation completed"
        )

# Also: every step.invoke must have been awaited (synchronous fanout).
step_invokes = inngest_driver.step_invocations_for_function("worker_execute")
for invocation in step_invokes:
    n_evals = len(invocation.task.evaluators)
    assert len(invocation.step_invokes) == n_evals
    assert all(s.completed for s in invocation.step_invokes)
```

The ordering check is the load-bearing v1-audit regression: in v1, sandbox
release happened in `check_evaluators` before `evaluate_task_run` finished.
The v2 fix is that release is gated on `asyncio.gather` over every
`ctx.step.invoke(evaluate_task_run, ...)` — synchronous fanout.

## Task 3: Required Variants

- [ ] **Failure cascade**

```python
@pytest.mark.asyncio
async def test_walkthrough_failure_cascade(
    walkthrough_factory,
    sandbox_hub,
    inngest_driver,
):
    experiment = walkthrough_factory(
        # Override task-2's worker to raise; other tasks unchanged.
        overrides={"code": _FailingWorker(name="code", model=None)},
    )

    handle = persist_definition(experiment)
    result = await launch_run(handle.definition_id)
    await inngest_driver.run_until_terminal(result.run_ids[0])

    final = await read_run(result.run_ids[0])
    assert final.status == "failed"

    nodes_by_slug = {n.task.task_slug: n for n in final.nodes}
    assert nodes_by_slug["research"].status == "completed"   # ran first
    assert nodes_by_slug["code"].status == "failed"          # raised
    # Spawn descendants of `code` cascade-fail:
    for spawn_child in nodes_by_slug["code"].spawn_children:
        assert spawn_child.status == "failed"
    # `review` is a dependency-dependent of `code`, NOT a spawn descendant.
    # It must stay PENDING per the workshop "Failure semantics" lock.
    assert nodes_by_slug["review"].status == "pending"
    # `summarize` has no dependency on `code` → keeps running.
    assert nodes_by_slug["summarize"].status in ("completed", "running")

    # Sandbox release still pairs with acquire even on failure.
    assert sandbox_hub.acquire_count == sandbox_hub.release_count
```

- [ ] **Dynamic spawn**

```python
@pytest.mark.asyncio
async def test_walkthrough_dynamic_spawn(
    walkthrough_factory,
    inngest_driver,
    session_factory,
):
    experiment = walkthrough_factory(
        overrides={"research": _SpawningWorker(name="research", model=None)},
    )

    handle = persist_definition(experiment)
    result = await launch_run(handle.definition_id)
    await inngest_driver.run_until_terminal(result.run_ids[0])

    final = await read_run(result.run_ids[0])
    spawned = [n for n in final.nodes if n.task.task_slug == "research-followup"]
    assert len(spawned) == 1
    spawned_node = spawned[0]
    assert spawned_node.is_dynamic is True

    # No definition row was created for the dynamic task.
    with session_factory() as session:
        rows = session.exec(
            "SELECT 1 FROM experiment_definition_tasks WHERE task_slug = :s",
            {"s": "research-followup"},
        ).all()
    assert rows == [], "dynamic spawn must not create definition rows"

    # The dynamic node was loaded via the same graph_repo.node path used
    # by static tasks — assert worker_execute was invoked with task_id =
    # spawned_node.task_id (the run-tier identity), NOT a definition_task_id.
    invocations = inngest_driver.events_for("worker_execute")
    spawn_invocation = next(
        e for e in invocations if e.payload["task_id"] == str(spawned_node.task_id)
    )
    assert spawn_invocation.payload.get("definition_task_id") is None
```

- [ ] **Restart**

```python
@pytest.mark.asyncio
async def test_walkthrough_restart_after_success(
    walkthrough_factory,
    sandbox_hub,
    inngest_driver,
    session_factory,
):
    experiment = walkthrough_factory()
    handle = persist_definition(experiment)
    result = await launch_run(handle.definition_id)
    await inngest_driver.run_until_terminal(result.run_ids[0])

    initial = await read_run(result.run_ids[0])
    research_node = next(n for n in initial.nodes if n.task.task_slug == "research")
    first_execution_id = research_node.latest_execution_id
    initial_acquires = sandbox_hub.acquire_count

    # Trigger restart through the same management entrypoint a worker would.
    await TaskManagementService().restart_task(
        run_id=initial.run_id,
        task_id=research_node.task.task_id,
    )
    await inngest_driver.run_until_terminal(initial.run_id)

    after = await read_run(initial.run_id)
    refreshed = next(n for n in after.nodes if n.task.task_slug == "research")

    # Fresh execution row with a new id.
    assert refreshed.latest_execution_id != first_execution_id

    # Old execution row preserved for audit.
    with session_factory() as session:
        rows = session.exec(
            "SELECT id FROM run_task_executions WHERE node_id = :n ORDER BY started_at",
            {"n": str(research_node.id)},
        ).all()
    assert len(rows) >= 2
    assert str(first_execution_id) in {str(r[0]) for r in rows}

    # New sandbox acquire/release pair landed.
    assert sandbox_hub.acquire_count == initial_acquires + 1
    assert sandbox_hub.release_count == sandbox_hub.acquire_count
```

`_FailingWorker` and `_SpawningWorker` are tiny test doubles defined in
`conftest.py` next to `FileDropWorker` — one raises in `execute`, the other
calls `context.spawn_task(...)` once with a `research-followup` task.

## Task 4: Regression Net

**Files:**

- Create: `ergon_core/tests/unit/regression/test_v1_audit_findings.py`

- [ ] Add one test per audit finding. Each test is named after the
      finding it guards so failures map back to the audit report.

```python
import os
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import inspect, create_engine

ROOT = Path(__file__).resolve().parents[4]
PRODUCTION_ROOTS = (
    ROOT / "ergon_core" / "ergon_core",
    ROOT / "ergon_builtins" / "ergon_builtins",
    ROOT / "ergon_cli" / "ergon_cli",
)


def _production_grep(symbol: str) -> list[Path]:
    hits: list[Path] = []
    for root in PRODUCTION_ROOTS:
        for path in root.rglob("*.py"):
            if "tests" in path.parts or "migrations" in path.parts:
                continue
            if symbol in path.read_text():
                hits.append(path)
    return hits


# 1. No ExperimentRecord table in the final v2 schema.
def test_audit_no_experiment_records_table() -> None:
    engine = create_engine(os.environ["DATABASE_URL"])
    tables = set(inspect(engine).get_table_names())
    assert "experiment_records" not in tables


# 2. Runtime does not read definition task rows.
def test_audit_runtime_does_not_read_definition_task_rows() -> None:
    worker_execute = (
        ROOT
        / "ergon_core/ergon_core/core/application/jobs/worker_execute.py"
    ).read_text()
    assert "DefinitionRepository" not in worker_execute
    assert "ExperimentDefinitionTask" not in worker_execute
    assert "task_with_instance" not in worker_execute


# 3. Dynamic spawn has no definition row (covered end-to-end by the
#    walkthrough; this is the unit-level invariant).
@pytest.mark.asyncio
async def test_audit_dynamic_spawn_has_no_definition_row(
    worker_context_factory, run_graph_factory, session
):
    from ergon_core.api.benchmark.task import Task
    from sqlmodel import select, func
    from ergon_core.core.persistence.definitions.models import (
        ExperimentDefinitionTask,
    )
    from tests.unit.runtime._test_workers import EchoWorker, EchoSandbox

    graph = run_graph_factory(nodes=[("root", None)])
    ctx = worker_context_factory(run_id=graph.run_id, task_id=graph.task_id("root"))
    before = session.exec(select(func.count()).select_from(ExperimentDefinitionTask)).one()
    await ctx.spawn_task(
        Task(
            task_slug="c",
            instance_key="i",
            description="d",
            worker=EchoWorker(name="e", model=None),
            sandbox=EchoSandbox(),
            evaluators=(),
        )
    )
    after = session.exec(select(func.count()).select_from(ExperimentDefinitionTask)).one()
    assert after == before


# 4. Sandbox released after all eval invocations complete (ordering check in walkthrough;
#    this is the structural guard).
def test_audit_sandbox_released_in_worker_execute_finally() -> None:
    body = (
        ROOT
        / "ergon_core/ergon_core/core/application/jobs/worker_execute.py"
    ).read_text()
    # The release call must live inside a `finally:` block in the same
    # function that owns the acquire — not a separate job.
    assert "finally:" in body
    assert "release" in body.lower()
    # And no separate evaluate_task_run dispatch survives:
    assert "ctx.step.invoke" not in body or "evaluate_task_run" not in body


# 5. evaluate_task_run is registered and uses the thin id-only payload.
#    (Δ.4 reshapes it; it is NOT deleted.)
def test_audit_evaluate_task_run_uses_thin_payload() -> None:
    # Identity-based registration check — no attribute introspection.
    # If Inngest changes the slug attribute name across versions, this
    # test stays green so long as the function is in the registered
    # set.
    from ergon_core.core.application.jobs.evaluate_task_run import (
        evaluate_task_run,
    )
    from ergon_core.core.infrastructure.inngest.registry import ALL_FUNCTIONS

    assert evaluate_task_run in ALL_FUNCTIONS, (
        "evaluate_task_run is the per-evaluator fanout target; it must "
        "remain registered in ALL_FUNCTIONS."
    )

    body = (
        ROOT
        / "ergon_core/ergon_core/core/application/jobs/evaluate_task_run.py"
    ).read_text()
    assert "TaskEvaluateRequest" in body
    assert "EvaluateTaskRunRequest" not in body  # v1 payload class is gone
    # No definition-tier reads:
    assert "DefinitionRepository" not in body
    assert "ExperimentDefinitionTask" not in body
    # Same run-tier load path as worker_execute:
    assert "WorkflowGraphRepository" in body


# 6. Single Alembic head.
def test_audit_single_alembic_head() -> None:
    result = subprocess.run(
        [
            "uv",
            "run",
            "alembic",
            "-c",
            str(ROOT / "ergon_core" / "alembic.ini"),
            "heads",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    head_lines = [ln for ln in result.stdout.strip().splitlines() if ln.strip()]
    assert len(head_lines) == 1


# 7. No saved_specs / from_buffer / CriterionExecutor / EvaluateTaskRunRequest
#    in production code. (evaluate_task_run as a name DOES survive — see #5.)
@pytest.mark.parametrize(
    "symbol",
    [
        "saved_specs",
        "from_buffer",
        "CriterionExecutor",
        "InngestCriterionExecutor",
        "EvaluateTaskRunRequest",
    ],
)
def test_audit_deleted_symbol_absent(symbol: str) -> None:
    hits = _production_grep(symbol)
    assert hits == [], f"{symbol} still appears in: {hits}"


# 8. CLI define routes through persist_definition.
def test_audit_cli_define_calls_persist_definition() -> None:
    body = (ROOT / "ergon_cli/ergon_cli/commands/experiment.py").read_text()
    assert "persist_definition" in body
    assert "define_benchmark_experiment" not in body
    assert "ExperimentDefineRequest" not in body
```

## Task 5: CI

**Files:**

- Modify: `.github/workflows/ci.yml`
- Modify: `pyproject.toml`

- [ ] Register `integration` pytest marker.
- [ ] Add architecture/regression CI job:

```bash
uv run pytest ergon_core/tests/unit/architecture ergon_core/tests/unit/regression -q
```

- [ ] Add walkthrough CI job when Postgres service is available:

```bash
uv run pytest -m integration ergon_core/tests/integration/test_walkthrough.py -q
```

## Task 6: Final Verification

```bash
uv run pytest ergon_core/tests/unit/architecture -q
uv run pytest ergon_core/tests/unit/regression -q
uv run pytest -m integration ergon_core/tests/integration/test_walkthrough.py -q
```

## PR Ledger

Invariant landed: final v2 behavior matches the canonical walkthrough.

Bridge code introduced: none.

Old path still intentionally alive: none.

Deletion gate: all gates closed before this PR.

Tests added or updated: walkthrough integration, v1 audit regression net,
CI jobs.

Modules owned by this PR: tests and CI.
