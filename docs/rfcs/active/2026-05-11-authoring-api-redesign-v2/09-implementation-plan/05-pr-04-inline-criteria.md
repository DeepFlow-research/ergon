# PR 4 — Synchronous-Fanout Criteria And Sandbox Release Ownership

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` or
> `superpowers:executing-plans` to implement this plan task-by-task.

**Goal:** Make `worker_execute` synchronously fan out per-evaluator
invocations via `ctx.step.invoke(evaluate_task_run, ...)`, wait for them
all via `asyncio.gather`, then release the sandbox in the same job's
`finally` block. Reshape `evaluate_task_run` to take a thin id-only
payload and re-load state via `graph_repo.node`.

**Architecture:** Two function shapes per task — orchestrator
(`worker_execute`) and per-evaluator worker (`evaluate_task_run`). The
orchestrator owns sandbox lifetime; eval workers only attach to the
external sandbox via `sandbox_id` and detach on completion. Inngest
retries, concurrency caps, and observability slugs apply per-eval — the
operational properties of v1's split are preserved. The lifecycle bug
v1 had (release in a sibling job) is fixed because the orchestrator's
`try/finally` bounds sandbox lifetime through the gather.

**Tech Stack:** Inngest job functions with `ctx.step.invoke`, existing
evaluation service, pytest lifecycle tests.

---

## Files

**Modify:**

```text
ergon_core/ergon_core/core/application/jobs/worker_execute.py
ergon_core/ergon_core/core/application/jobs/evaluate_task_run.py
ergon_core/ergon_core/core/application/jobs/check_evaluators.py
ergon_core/ergon_core/core/application/jobs/models.py
ergon_core/ergon_core/core/application/evaluation/service.py
ergon_core/ergon_core/core/infrastructure/inngest/registry.py
ergon_core/ergon_core/core/persistence/telemetry/repository.py
ergon_core/tests/unit/runtime/test_worker_execute_sandbox_lifecycle.py
ergon_core/tests/unit/runtime/test_evaluate_task_run_thin_payload.py
ergon_core/tests/unit/runtime/test_failed_task_sandbox_cleanup.py
ergon_core/tests/unit/architecture/test_runtime_read_boundaries.py
```

## Current State

`check_evaluators.py` is fired after `task/completed`. It invokes
`evaluate_task_run` per evaluator (fire-and-forget) and then calls
`terminate_sandbox_by_id`. Sandbox release is owned by a sibling job —
the v1 audit's lifecycle leak.

`evaluate_task_run.py` (current body) takes `EvaluateTaskRunRequest`
with many fields: `definition_task_id`, `evaluator_id`,
`evaluator_binding_key`, `evaluator_type`, `agent_reasoning`, etc. It
reads definition rows, resolves the evaluator through
`ComponentCatalogService`, and constructs a synthetic `Task`. This
violates the Δ.2 run-tier read boundary every time it runs.

## Target State For This PR

`worker_execute.py`:

```python
sandbox = await lifecycle_hub.acquire(task.sandbox, run_id=..., task_id=...)
await task_execution_repo.set_sandbox_id(
    execution_id=payload.execution_id, sandbox_id=sandbox.sandbox_id,
)
try:
    output = await consume_worker_stream(...)
    persist_worker_output(payload.execution_id, output)

    # Synchronous fanout. Parent suspends until every invoke returns.
    await asyncio.gather(*[
        ctx.step.invoke(
            f"eval-{i}",
            evaluate_task_run,
            TaskEvaluateRequest(
                run_id=payload.run_id,
                task_id=payload.task_id,
                execution_id=payload.execution_id,
                evaluator_index=i,
            ),
        )
        for i in range(len(task.evaluators))
    ])
finally:
    await lifecycle_hub.release(sandbox)
```

`evaluate_task_run.py` (reshaped body): id-only payload, reload state
via `graph_repo.node(..., sandbox_id=...)`, run evaluator, detach.

`check_evaluators.py` becomes obsolete; PR 11 deletes it.
`terminate_sandbox_by_id` is no longer called by `worker_execute` or
`evaluate_task_run`; PR 11 deletes the helper.

---

## Task 1: Add Thin Eval Payload And Worker Output Persistence

**Files:**

- Modify: `ergon_core/ergon_core/core/application/jobs/models.py`
- Modify: `ergon_core/ergon_core/core/persistence/telemetry/repository.py`

- [ ] **Step 1: Add `TaskEvaluateRequest`**

```python
from uuid import UUID
from pydantic import BaseModel


class TaskEvaluateRequest(BaseModel):
    """Thin id-only payload for the per-evaluator Inngest function.

    Every other piece of state — task config, sandbox_id, worker_output,
    evaluator instance — is recovered by the receiver via persisted
    state lookups. This keeps retries/replays trivially correct.
    """

    run_id: UUID
    task_id: UUID
    execution_id: UUID
    evaluator_index: int
```

Keep `EvaluateTaskRunRequest` importable until PR 11; do not yet
remove it from `__all__`. The reshaped `evaluate_task_run` uses the new
payload class; the old class lives as a forwarding shim until cleanup.

- [ ] **Step 2: Add `set_sandbox_id` and worker-output persistence helpers**

In `telemetry/repository.py`:

```python
class TaskExecutionRepository:
    ...

    async def set_sandbox_id(
        self,
        *,
        execution_id: UUID,
        sandbox_id: str,
    ) -> None:
        async with self._session() as session:
            session.exec(
                update(RunTaskExecution)
                .where(RunTaskExecution.id == execution_id)
                .values(sandbox_id=sandbox_id)
            )
            session.commit()
```

The column already exists (migration
`925ff225d97e_add_sandbox_id_to_run_task_executions.py`).

For worker-output persistence/load, the `run_graph_nodes` row already
carries the worker output JSON via `task_json` + the existing
`evaluation_summary` paths. Add explicit `WorkerOutputRepository`:

```python
class WorkerOutputRepository:
    """Persisted worker_output keyed by execution_id, read by eval workers."""

    async def persist(
        self, *, run_id: UUID, task_id: UUID, execution_id: UUID,
        output: WorkerOutput,
    ) -> None:
        async with self._session() as session:
            row = RunTaskExecution(
                ...,  # existing fields
                worker_output_json=output.model_dump(mode="json"),
            )
            session.merge(row)
            session.commit()

    async def load(self, *, execution_id: UUID) -> WorkerOutput:
        async with self._session() as session:
            row = session.get(RunTaskExecution, execution_id)
            if row is None or row.worker_output_json is None:
                raise WorkerOutputNotFound(execution_id=execution_id)
            return WorkerOutput.model_validate(row.worker_output_json)
```

If `RunTaskExecution.worker_output_json` does not exist, add it via an
additive Alembic migration in this PR:

```python
def upgrade() -> None:
    op.add_column(
        "run_task_executions",
        sa.Column("worker_output_json", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("run_task_executions", "worker_output_json")
```

## Task 2: Reshape `evaluate_task_run` Body

**Files:**

- Modify: `ergon_core/ergon_core/core/application/jobs/evaluate_task_run.py`

- [ ] **Step 1: Replace the function body**

```python
from datetime import UTC, datetime
import logging

import inngest

from ergon_core.api.criterion.context import CriterionContext
from ergon_core.core.application.evaluation.service import EvaluationService
from ergon_core.core.application.graph.repository import WorkflowGraphRepository
from ergon_core.core.application.jobs.models import TaskEvaluateRequest
from ergon_core.core.infrastructure.dashboard.emitters import (
    get_dashboard_emitter,
)
from ergon_core.core.infrastructure.observability.spans import (
    CompletedSpan,
    evaluation_task_context,
    get_trace_sink,
)
from ergon_core.core.persistence.telemetry.repositories import (
    TaskExecutionRepository,
    WorkerOutputRepository,
)
from ergon_core.core.persistence.sessions import get_session

logger = logging.getLogger(__name__)
_evaluation_persistence = EvaluationService()


@inngest.function(
    fn_id="evaluate_task_run",
    trigger=inngest.TriggerEvent(event="task/evaluate"),
    retries=3,
    concurrency=inngest.Concurrency(limit=50),
)
async def evaluate_task_run(
    ctx: inngest.Context, payload: TaskEvaluateRequest
) -> None:
    """Per-evaluator fanout target. Thin id-only payload."""

    span_start = datetime.now(UTC)
    execution = await TaskExecutionRepository().get(payload.execution_id)
    if execution is None:
        raise ContractViolationError(
            f"RunTaskExecution {payload.execution_id} not found",
            run_id=payload.run_id, task_id=payload.task_id,
        )

    with get_session() as session:
        view = await WorkflowGraphRepository().node(
            session,
            run_id=payload.run_id,
            task_id=payload.task_id,
            sandbox_id=execution.sandbox_id,  # attaches a live _runtime
        )
    task = view.task
    output = await WorkerOutputRepository().load(execution_id=payload.execution_id)
    evaluator = task.evaluators[payload.evaluator_index]

    # Build a CriterionContext matching the v1-locked Criterion.evaluate
    # signature (see 01-api-surface.md § "Criterion class signature —
    # locked"). The sandbox is live on context.task.sandbox via the
    # graph_repo.node(..., sandbox_id=...) attach above; criteria call
    # context.task.sandbox.run_command(...) directly — no separate sandbox
    # parameter, no runtime proxies on the context itself.
    context = CriterionContext(
        run_id=payload.run_id,
        task_id=payload.task_id,
        execution_id=payload.execution_id,
        task=task,
        worker_result=output,
    )

    try:
        # EvaluationService internally iterates evaluator.criteria and
        # awaits each `criterion.evaluate(context)` — no CriterionExecutor.
        service_result = await _evaluation_persistence.evaluate(
            context=context,
            evaluator=evaluator,
            benchmark_name="",
        )
    except Exception as exc:  # slopcop: ignore[no-broad-except]
        logger.exception(
            "evaluate_task_run failed run_id=%s task_id=%s index=%s",
            payload.run_id, payload.task_id, payload.evaluator_index,
        )
        _evaluation_persistence.persist_failure(
            run_id=payload.run_id,
            node_id=view.node_id,
            task_execution_id=payload.execution_id,
            definition_task_id=view.definition_task_id,
            evaluator_id=None,                          # evaluator instance carries identity
            evaluator_name=type(evaluator).__name__,
            exc=exc,
        )
        # Detach so the local _runtime handle is released; the external
        # sandbox keeps running — termination is the orchestrator's job.
        await task.sandbox.detach()
        raise

    persisted = _evaluation_persistence.persist_success(
        run_id=payload.run_id,
        node_id=view.node_id,
        task_execution_id=payload.execution_id,
        definition_task_id=view.definition_task_id,
        evaluator_id=None,
        service_result=service_result,
    )
    await get_dashboard_emitter().task_evaluation_updated(
        run_id=payload.run_id,
        task_id=payload.task_id,
        evaluation=persisted.dashboard_dto,
    )
    get_trace_sink().emit_span(
        CompletedSpan(
            name="evaluation.task",
            context=evaluation_task_context(
                payload.run_id, payload.task_id,
                payload.execution_id, evaluator_index=payload.evaluator_index,
            ),
            start_time=span_start,
            end_time=datetime.now(UTC),
            attributes={
                "passed": service_result.result.passed,
                "score": service_result.result.score,
            },
        )
    )
    await task.sandbox.detach()
```

Notes:

- The reshape preserves the function name and Inngest slug. Existing
  dashboards / GraphQL queries that filter by
  `function.slug == "evaluate_task_run"` keep working.
- `InngestCriterionExecutor` and the `CriterionExecutor` Protocol are
  gone from this body — `service.evaluate(...)` calls
  `criterion.evaluate(...)` directly because the criterion is already a
  fully constructed object on `task.evaluators[i]`. PR 11 deletes the
  executor classes.
- `detach()` is the new `Sandbox` protocol method PR 5 adds. PR 4 uses
  it via the bridge defined in Task 4 below.

## Task 3: Make `worker_execute` Fan Out Via `step.invoke`

**Files:**

- Modify: `ergon_core/ergon_core/core/application/jobs/worker_execute.py`

- [ ] **Step 1: Persist worker output before fanout**

After the worker stream consumption, persist the terminal `WorkerOutput`
through the new repo:

```python
await WorkerOutputRepository().persist(
    run_id=payload.run_id,
    task_id=payload.task_id,
    execution_id=payload.execution_id,
    output=output,
)
```

This must commit before the fanout: eval workers load from the same
repo.

- [ ] **Step 2: Stamp sandbox_id on the execution row**

Right after acquire:

```python
await TaskExecutionRepository().set_sandbox_id(
    execution_id=payload.execution_id,
    sandbox_id=sandbox.sandbox_id,
)
```

Eval workers read this when calling `graph_repo.node(...,
sandbox_id=...)` to attach the live runtime.

- [ ] **Step 3: Replace inline-evaluator block with synchronous fanout**

```python
import asyncio

from ergon_core.core.application.jobs.evaluate_task_run import evaluate_task_run
from ergon_core.core.application.jobs.models import TaskEvaluateRequest


# ... after worker output persistence:
await asyncio.gather(*[
    ctx.step.invoke(
        f"eval-{i}",
        evaluate_task_run,
        TaskEvaluateRequest(
            run_id=payload.run_id,
            task_id=payload.task_id,
            execution_id=payload.execution_id,
            evaluator_index=i,
        ),
    )
    for i in range(len(task.evaluators))
])
```

The gather is what keeps the sandbox alive: `worker_execute` cannot
reach its `finally` until every `step.invoke` returns. The
`f"eval-{i}"` step IDs make each invocation independently retriable
by Inngest.

- [ ] **Step 4: Release sandbox in `finally`**

```python
sandbox_id = sandbox.sandbox_id
try:
    output, chunk_count = await _consume_worker_stream(...)
    await WorkerOutputRepository().persist(...)
    await asyncio.gather(*[
        ctx.step.invoke(...) for i in range(len(task.evaluators))
    ])
except Exception as exc:
    return _worker_failure_result(exc, chunk_count)
finally:
    await lifecycle_hub.release(sandbox)
```

`lifecycle_hub.release(sandbox)` is the canonical path; it calls
`sandbox.terminate()` which terminates the external sandbox. PR 6
removes the v1 `terminate_sandbox_by_id` fallback.

## Task 4: Add `Sandbox.detach()` Stub (Bridge)

**Files:**

- Modify: `ergon_core/ergon_core/api/sandbox/sandbox.py`

PR 5 defines the public `Sandbox` ABC. PR 4 needs `detach()` to exist
before PR 5 lands so the new `evaluate_task_run` body compiles. Add it
as a concrete method on the (still-private) bridge class for now:

- [ ] **Step 1: Add bridge stub**

If `Sandbox` ABC does not exist yet (it lands in PR 5), add to
`ergon_core/ergon_core/core/infrastructure/sandbox/runtime.py`:

```python
from typing import Protocol


class _DetachableRuntime(Protocol):
    """Bridge-internal Protocol describing the runtime methods PR 4
    needs from a sandbox's `_runtime` handle.

    PR 5 lifts these into a real `SandboxRuntime` Protocol in
    `ergon_core.api.sandbox.runtime`. Until then, this Protocol exists
    only inside the bridge to give `_DetachableSandboxBridge.detach`
    typed access to `close` / `close_local`.
    """

    async def close(self) -> None: ...
    async def close_local(self) -> None: ...


class _DetachableSandbox(Protocol):
    """Bridge-internal Protocol over the Sandbox-ish object the eval
    worker has at this point. PR 5's real `Sandbox` ABC satisfies it.
    """

    _runtime: _DetachableRuntime | None


class _DetachableSandboxBridge:
    """Bridge so PR 4 can call sandbox.detach() before PR 5 lands.

    Matches the loud contract PR 5's Sandbox.detach() ships with — a
    detach on a sandbox with no live runtime raises rather than
    silently no-oping. Eval workers always attach before they detach
    (via graph_repo.node(..., sandbox_id=...)); if this raises, the
    attach side broke first and should be debugged at the cause.
    """

    @staticmethod
    async def detach(sandbox: _DetachableSandbox) -> None:
        runtime = sandbox._runtime
        if runtime is None:
            raise RuntimeError(
                f"{type(sandbox).__name__}.detach() called on a sandbox "
                f"with no live runtime. Eval workers must attach before "
                f"detaching."
            )
        # close_local is on the Protocol from PR 4 onward — every
        # manager-backed runtime must implement it for the synchronous-
        # fanout eval path to work. If a runtime is encountered without
        # it, that's a contract violation we want surfaced (not
        # silently downgraded to a full close).
        await runtime.close_local()
        # The _runtime PrivateAttr is settable on the non-frozen Sandbox
        # Pydantic model — object.__setattr__ keeps symmetry with the
        # frozen-Sandbox patterns used elsewhere in the API.
        object.__setattr__(sandbox, "_runtime", None)
```

This bridge is replaced by `Sandbox.detach()` on the base class in
PR 5 (Task 4c). The Protocol definitions also go away — PR 5's
`SandboxRuntime` Protocol absorbs them. Every concrete
`ManagerBackedSandboxRuntime` must implement `close_local` from PR 4
onward; if a runtime doesn't, the loud failure here surfaces it before
the bridge gets deleted.

PR 5 lifts this into `Sandbox.detach()` as a base-class method. The
bridge is grep-able by class name for deletion.

## Task 5: Remove `check_evaluators` Dispatch And Inngest Registration

**Files:**

- Modify: `ergon_core/ergon_core/core/infrastructure/inngest/registry.py`
- Modify: `ergon_core/ergon_core/core/application/jobs/check_evaluators.py`

- [ ] **Step 1: Remove `check_evaluators` send after `task/completed`**

Where `worker_execute` (or `advance_run`) fires `check_evaluators`, delete
that send. `task/completed` should advance the run only.

- [ ] **Step 2: Keep `check_evaluators.py` importable**

Reduce its body to:

```python
"""Legacy check-evaluators handler. Replaced by synchronous fanout in PR 4.

This module remains importable until PR 11 deletes it so worktrees that
have not yet rebased can still import the module. The Inngest function
is not registered.
"""

import inngest

# Deliberately NOT registered with ALL_FUNCTIONS.
```

- [ ] **Step 3: Keep `evaluate_task_run` registered (slug unchanged)**

`ALL_FUNCTIONS` must continue to include `evaluate_task_run`. Verify
its entry in `registry.py`:

```python
from ergon_core.core.application.jobs.evaluate_task_run import evaluate_task_run

ALL_FUNCTIONS = [
    ...,
    evaluate_task_run,
    ...,
]
```

Update the `check_evaluators` entry to be removed:

```python
# Remove:
from ergon_core.core.infrastructure.inngest.handlers.check_evaluators import (
    check_evaluators,
)
# and the corresponding line in ALL_FUNCTIONS.
```

## Task 6: Tests

**Files:**

- Modify: `ergon_core/tests/unit/runtime/test_worker_execute_sandbox_lifecycle.py`
- Create: `ergon_core/tests/unit/runtime/test_evaluate_task_run_thin_payload.py`
- Modify: `ergon_core/tests/unit/architecture/test_runtime_read_boundaries.py`

- [ ] **Step 1: Sandbox release happens AFTER gather returns**

```python
@pytest.mark.asyncio
async def test_worker_execute_releases_sandbox_after_eval_gather(monkeypatch):
    ordering: list[str] = []

    async def fake_invoke(step_id, fn, payload):
        ordering.append(f"invoke-{step_id}")

    async def fake_release(sandbox):
        ordering.append("release")

    monkeypatch.setattr(
        worker_execute, "_acquire_sandbox", AsyncMock(side_effect=lambda *a, **kw: ordering.append("acquire") or _FakeSandbox()),
    )
    monkeypatch.setattr(
        "ergon_core.core.application.jobs.worker_execute.lifecycle_hub.release",
        fake_release,
    )

    fake_ctx = SimpleNamespace(step=SimpleNamespace(invoke=fake_invoke))
    await worker_execute.run_worker_execute_job(fake_ctx, payload_factory(n_evaluators=3))

    # acquire → 3 invokes → release, with release strictly last.
    assert ordering[0] == "acquire"
    assert ordering[-1] == "release"
    assert ordering.count("release") == 1
    assert sum(1 for s in ordering if s.startswith("invoke-")) == 3
```

- [ ] **Step 2: Eval thin-payload test**

```python
@pytest.mark.asyncio
async def test_evaluate_task_run_loads_state_from_run_tier(
    session, run_node_factory, task_execution_factory, worker_output_factory,
):
    node = run_node_factory(
        task_json=_object_bound_task_json(evaluators=[_test_rubric_json()])
    )
    execution = task_execution_factory(node_id=node.id, sandbox_id="sbx-123")
    worker_output_factory(execution_id=execution.id, final_text="hello")

    # Stub the sandbox attach so we don't hit e2b in unit tests:
    with patch.object(Sandbox, "_bind_runtime", AsyncMock()) as bind:
        await evaluate_task_run.fn(
            ctx=SimpleNamespace(),
            payload=TaskEvaluateRequest(
                run_id=node.run_id,
                task_id=node.task_id,
                execution_id=execution.id,
                evaluator_index=0,
            ),
        )

    # Sandbox bound to the stamped id, then detached at the end.
    bind.assert_awaited_once_with("sbx-123")
    # Evaluation persisted:
    rows = session.exec(
        select(RunTaskEvaluation).where(RunTaskEvaluation.run_id == node.run_id)
    ).all()
    assert len(rows) == 1
```

- [ ] **Step 3: Architecture guard**

```python
def test_evaluate_task_run_uses_thin_payload_and_run_tier_read() -> None:
    body = (
        ROOT
        / "ergon_core/ergon_core/core/application/jobs/evaluate_task_run.py"
    ).read_text()
    # Thin payload only:
    assert "TaskEvaluateRequest" in body
    assert "EvaluateTaskRunRequest" not in body
    # No definition-tier reads:
    assert "DefinitionRepository" not in body
    assert "ExperimentDefinitionTask" not in body
    # No registry-based evaluator resolution:
    assert "ComponentCatalogService" not in body
    # Uses the same run-tier loader the orchestrator uses:
    assert "WorkflowGraphRepository" in body
    assert ".node(" in body


def test_worker_execute_fans_out_via_step_invoke() -> None:
    body = (
        ROOT
        / "ergon_core/ergon_core/core/application/jobs/worker_execute.py"
    ).read_text()
    assert "ctx.step.invoke" in body
    assert "evaluate_task_run" in body
    # asyncio.gather over the invocations:
    assert "asyncio.gather" in body
    # Sandbox release in finally, NOT in a sibling job:
    assert "finally:" in body
    assert "terminate_sandbox_by_id" not in body
```

- [ ] **Step 4: Run focused tests**

```bash
uv run pytest \
  ergon_core/tests/unit/runtime/test_worker_execute_sandbox_lifecycle.py \
  ergon_core/tests/unit/runtime/test_evaluate_task_run_thin_payload.py \
  ergon_core/tests/unit/architecture/test_runtime_read_boundaries.py -q
```

Expected: pass; release strictly after gather; eval reads only run-tier.

## Task 7: Flip XFails Landed By This PR

**Files:**

- Modify: `ergon_core/tests/unit/architecture/test_v2_final_state_ledger.py`
- Modify: `ergon_core/tests/unit/architecture/test_repository_companion_files.py`
- Modify: `ergon_core/tests/unit/runtime/test_walkthrough_smoketest.py`
- Modify: `ergon_core/tests/unit/runtime/test_identity_invariants.py`
- Move: `CreateTaskEvaluation` from `telemetry/repository.py` to
  `telemetry/models.py` (see step below).

PR 4 lands four invariants pre-registered in the ledgers:

- [ ] **Step 1: Remove the PR 4 entries from `_XFAIL_BY_NAME`**

In `test_v2_final_state_ledger.py`, delete:

```python
"evaluate_task_run_uses_thin_payload": "PR 4 reshapes evaluate_task_run",
"check_evaluators_is_unregistered": "PR 4 removes check_evaluators dispatch",
```

- [ ] **Step 2: Flip three smoketest cases**

In `test_walkthrough_smoketest.py`, remove the `@pytest.mark.xfail` from
each of:

- `test_worker_execute_emits_one_evaluate_invocation_per_evaluator`
- `test_evaluate_task_run_payload_is_id_only`
- `test_sandbox_release_happens_after_all_evaluators_complete`

Replace each `pytest.fail(...)` body with the real assertion. The
`inngest_driver` fixture lands here too — it's the test driver that
records `ctx.step.invoke` calls and exposes
`inngest_driver.step_invocations_for_function("evaluate_task_run")`.

- [ ] **Step 3: Flip two identity invariants**

In `test_identity_invariants.py`, remove the `@pytest.mark.xfail` from:

- `test_sandbox_identity_is_preserved_across_worker_to_evaluate_boundary`
- `test_execution_id_is_unique_per_attempt_and_shared_across_evaluators`

Implement the real bodies — both lean on `run_task_executions.sandbox_id`
being stamped by the orchestrator (this PR Task 3 Step 2) and on
`TaskEvaluateRequest` carrying `execution_id` + `evaluator_index`.

- [ ] **Step 4: Move `CreateTaskEvaluation` to `telemetry/models.py`**

PR 0.5's repository-companion-files guard xfails the
`test_repository_file_does_not_define_dtos[.../telemetry]` case until
the DTO moves out of the repo file. PR 4 is already editing
`telemetry/repository.py` to add `set_sandbox_id` and the
`WorkerOutputRepository` — folding the DTO move in keeps the touch
surface bounded.

In `ergon_core/ergon_core/core/persistence/telemetry/repository.py`,
delete:

```python
class CreateTaskEvaluation(BaseModel):
    ...
```

Add the same class to
`ergon_core/ergon_core/core/persistence/telemetry/models.py`, and
update `telemetry/__init__.py` (or every importer) to re-export from
the new location. Run:

```bash
rg "CreateTaskEvaluation" ergon_core ergon_builtins ergon_cli
```

to confirm every import path is updated.

Remove the corresponding entry from `_KNOWN_VIOLATORS` in
`test_repository_companion_files.py`:

```python
("test_repository_file_does_not_define_dtos",
 "ergon_core/ergon_core/core/persistence/telemetry"):
    "PR 4: move CreateTaskEvaluation to telemetry/models.py",
```

- [ ] **Step 5: Run the ledgers**

```bash
uv run pytest \
  ergon_core/tests/unit/architecture/test_v2_final_state_ledger.py \
  ergon_core/tests/unit/architecture/test_repository_companion_files.py \
  ergon_core/tests/unit/runtime/test_walkthrough_smoketest.py \
  ergon_core/tests/unit/runtime/test_identity_invariants.py -q
```

Expected: PR 4 ledger entries gone; the corresponding smoketest,
identity, and repository-companion cases PASS; remaining cases still
XFAIL.

## PR Ledger

Invariant landed: worker_execute orchestrates evaluation through
synchronous fanout; sandbox release bounded by the orchestrator's
try/finally; eval is a per-function Inngest target with thin id-only
payload.

Bridge code introduced: `_DetachableSandboxBridge` (deleted by PR 5
into `Sandbox.detach()`).

Old path still intentionally alive: `EvaluateTaskRunRequest` import
shim, `check_evaluators.py` (importable, unregistered), `CriterionExecutor`
/ `InngestCriterionExecutor` (no longer used; PR 11 deletes).

Deletion gate: PR 11 deletes the executor classes,
`EvaluateTaskRunRequest`, `check_evaluators.py`, and
`terminate_sandbox_by_id`. `evaluate_task_run` itself stays — the slug,
the function, the registration. Only the v1 body and v1 payload class
go.

Tests added or updated: release-after-gather ordering, eval
thin-payload, runtime-read boundary guards for both jobs.

Modules owned by this PR: worker-execute orchestration shape, eval
function body, Inngest registration, execution-row sandbox_id
stamping, worker-output persistence.
