"""PR 4: behavioural tests for the orchestrator's evaluator fanout.

The textual guards in ``test_runtime_read_boundaries.py`` and
``test_walkthrough_smoketest.py`` cover the structural shape (the
strings must appear in the source). These tests drive the orchestrator
with stubbed Inngest primitives and observe the ordering of
``ctx.step.invoke`` calls vs ``terminate_sandbox_by_id`` — the
invariant being: the gather over per-evaluator invokes resolves
strictly before sandbox termination.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock
from uuid import uuid4

import inngest
import pytest

from ergon_core.core.application.events.task_events import TaskReadyEvent
from ergon_core.core.application.jobs import execute_task as execute_task_module
from ergon_core.core.application.jobs.models import (
    PersistOutputsResult,
    SandboxReadyResult,
    WorkerExecuteJobResult,
)
from ergon_core.core.application.tasks.execution import TaskExecutionService
from ergon_core.core.application.workflows.orchestration import PreparedTaskExecution
from ergon_core.core.infrastructure.sandbox.lifecycle import (
    SandboxTerminationReason,
    SandboxTerminationResult,
)

# A typed stand-in for any `inngest.Function` the orchestrator would
# normally hand to `ctx.step.invoke(function=...)`. The fakes below
# never read it — `cast` here just satisfies the strongly-typed
# kwargs on `run_execute_task_job` without bringing real Inngest
# function objects into the unit test.
_FAKE_FN = cast(inngest.Function, object())


class _OrderedFakeCtx:
    """Records every step-invoke and step-run by step_id."""

    def __init__(self, ordering: list[str]) -> None:
        self._ordering = ordering
        self.step = SimpleNamespace(
            invoke=self._invoke,
            run=self._run,
        )

    async def _invoke(
        self,
        step_id: str,
        *,
        function: inngest.Function,
        data: dict[str, object],
    ) -> object:
        # Return is polymorphic across step.invoke call sites
        # (SandboxReadyResult, WorkerExecuteJobResult, EvaluateTaskRunResult,
        # ...) — `object` is the honest bound for a test fake that
        # impersonates all of them. The tests below don't read the return.
        del function, data
        self._ordering.append(f"invoke:{step_id}")
        return SimpleNamespace(sandbox_id="sbx-test", output_dir=None, success=True)

    async def _run(
        self,
        step_id: str,
        fn: Callable[[], Awaitable[object]],
        *,
        output_type: type | None = None,
    ) -> object:
        del output_type
        self._ordering.append(f"run:{step_id}")
        return await fn()


def _prepared(execution_id, node_id) -> PreparedTaskExecution:
    return PreparedTaskExecution(
        run_id=uuid4(),
        definition_id=uuid4(),
        task_id=uuid4(),
        node_id=node_id,
        execution_id=execution_id,
        task_slug="t",
        task_description="d",
        assigned_worker_slug="w",
        worker_type="echo",
        model_target="echo",
        benchmark_type="echo",
        skipped=False,
    )


def _ready_event(run_id, definition_id, task_id, node_id) -> TaskReadyEvent:
    return TaskReadyEvent(
        run_id=run_id,
        definition_id=definition_id,
        task_id=task_id,
        node_id=node_id,
    )


@pytest.mark.asyncio
async def test_execute_task_releases_sandbox_strictly_after_eval_gather(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The orchestrator's ``finally`` must run after every per-evaluator
    invoke returns. Ordering across the run must be:
    sandbox-setup → worker-execute → persist-outputs → eval-0..N
    → terminate_sandbox_by_id.
    """

    ordering: list[str] = []
    ctx = _OrderedFakeCtx(ordering)

    run_id = uuid4()
    definition_id = uuid4()
    task_id = uuid4()
    node_id = uuid4()
    execution_id = uuid4()

    prepared = _prepared(execution_id, node_id)
    payload = _ready_event(run_id, definition_id, task_id, node_id)

    async def fake_prepare(
        _ctx: inngest.Context,
        _svc: TaskExecutionService,
        _payload: TaskReadyEvent,
    ) -> PreparedTaskExecution:
        ordering.append("prepare")
        return prepared

    async def fake_invoke_sandbox_setup(
        _ctx: inngest.Context,
        _payload: TaskReadyEvent,
        _prepared: PreparedTaskExecution,
        _fn: inngest.Function,
    ) -> SandboxReadyResult:
        ordering.append("invoke:sandbox-setup")
        return SandboxReadyResult(sandbox_id="sbx-test", output_dir=None)

    async def fake_invoke_worker_execute(
        _ctx: inngest.Context,
        _payload: TaskReadyEvent,
        _prepared: PreparedTaskExecution,
        _sandbox: SandboxReadyResult,
        _fn: inngest.Function,
    ) -> WorkerExecuteJobResult:
        ordering.append("invoke:worker-execute")
        return WorkerExecuteJobResult(
            success=True,
            final_assistant_message="ok",
            error=None,
            error_json=None,
        )

    async def fake_invoke_persist_outputs(
        _ctx: inngest.Context,
        _payload: TaskReadyEvent,
        _prepared: PreparedTaskExecution,
        _sandbox: SandboxReadyResult,
        _fn: inngest.Function,
    ) -> PersistOutputsResult:
        ordering.append("invoke:persist-outputs")
        return PersistOutputsResult(outputs_count=0)

    async def fake_emit_completed(
        _payload: TaskReadyEvent,
        _prepared: PreparedTaskExecution,
        _sandbox_id: str,
    ) -> None:
        ordering.append("emit:task/completed")

    # Two evaluators bound on the task so the parallel fanout sees real work.
    view_task = SimpleNamespace(evaluator_binding_keys=("a", "b"))
    view = SimpleNamespace(task=view_task)
    repo = SimpleNamespace(node=AsyncMock(return_value=view))

    async def fake_fanout(
        ctx: inngest.Context,
        payload: TaskReadyEvent,
        prepared: PreparedTaskExecution,
        eval_fn: inngest.Function,
    ) -> None:
        del payload, prepared
        # Use the real call shape but bypass the session machinery so we
        # don't need a populated database — just count the invokes.
        for i in range(len(view_task.evaluator_binding_keys)):
            await ctx.step.invoke(
                f"eval-{i}",
                function=eval_fn,
                data={"evaluator_index": i},
            )

    termination_result = SandboxTerminationResult(
        sandbox_id="sbx-test",
        terminated=True,
        reason=SandboxTerminationReason.TERMINATED,
    )

    async def fake_terminate(sandbox_id: str) -> SandboxTerminationResult:
        ordering.append("terminate")
        return termination_result

    finalize_success = AsyncMock()
    svc = SimpleNamespace(
        finalize_success=finalize_success,
        finalize_failure=AsyncMock(),
    )

    monkeypatch.setattr(execute_task_module, "_prepare_execution", fake_prepare)
    monkeypatch.setattr(execute_task_module, "_invoke_sandbox_setup", fake_invoke_sandbox_setup)
    monkeypatch.setattr(execute_task_module, "_invoke_worker_execute", fake_invoke_worker_execute)
    monkeypatch.setattr(execute_task_module, "_invoke_persist_outputs", fake_invoke_persist_outputs)
    monkeypatch.setattr(execute_task_module, "_emit_task_completed", fake_emit_completed)
    monkeypatch.setattr(execute_task_module, "_fan_out_evaluators", fake_fanout)
    monkeypatch.setattr(execute_task_module, "TaskExecutionService", lambda: svc)
    monkeypatch.setattr(execute_task_module, "terminate_sandbox_by_id", fake_terminate)
    monkeypatch.setattr(execute_task_module.WorkflowGraphRepository, "node", repo.node)

    result = await execute_task_module.run_execute_task_job(
        ctx,
        payload,
        sandbox_setup_function=_FAKE_FN,
        worker_execute_function=_FAKE_FN,
        persist_outputs_function=_FAKE_FN,
        evaluate_task_run_function=_FAKE_FN,
    )

    assert result.success is True
    assert ordering.count("terminate") == 1, "sandbox must terminate exactly once"
    terminate_idx = ordering.index("terminate")
    eval_indices = [i for i, name in enumerate(ordering) if name.startswith("invoke:eval-")]
    assert eval_indices, "the gather must invoke at least one evaluator"
    assert all(i < terminate_idx for i in eval_indices), (
        f"every eval invoke must precede terminate; got order={ordering}"
    )
    # Final ordering shape sanity-check.
    assert ordering.index("emit:task/completed") < terminate_idx


@pytest.mark.asyncio
async def test_execute_task_releases_sandbox_when_worker_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The orchestrator's ``finally`` must still terminate when the
    worker reports failure (no eval fanout in this path)."""

    ordering: list[str] = []
    ctx = _OrderedFakeCtx(ordering)

    run_id = uuid4()
    prepared = _prepared(uuid4(), uuid4())
    payload = _ready_event(run_id, uuid4(), uuid4(), prepared.node_id)

    async def fake_prepare(
        _ctx: inngest.Context,
        _svc: TaskExecutionService,
        _payload: TaskReadyEvent,
    ) -> PreparedTaskExecution:
        return prepared

    async def fake_invoke_sandbox_setup(
        _ctx: inngest.Context,
        _payload: TaskReadyEvent,
        _prepared: PreparedTaskExecution,
        _fn: inngest.Function,
    ) -> SandboxReadyResult:
        return SandboxReadyResult(sandbox_id="sbx-fail", output_dir=None)

    async def fake_invoke_worker_execute(
        _ctx: inngest.Context,
        _payload: TaskReadyEvent,
        _prepared: PreparedTaskExecution,
        _sandbox: SandboxReadyResult,
        _fn: inngest.Function,
    ) -> WorkerExecuteJobResult:
        return WorkerExecuteJobResult(
            success=False,
            final_assistant_message=None,
            error="boom",
            error_json={"message": "boom"},
        )

    async def fake_invoke_persist_outputs(
        _ctx: inngest.Context,
        _payload: TaskReadyEvent,
        _prepared: PreparedTaskExecution,
        _sandbox: SandboxReadyResult,
        _fn: inngest.Function,
    ) -> PersistOutputsResult:
        return PersistOutputsResult(outputs_count=0)

    async def fake_emit_failed(
        _payload: TaskReadyEvent,
        _prepared: PreparedTaskExecution,
        _error: str,
        _sandbox_id: str | None,
    ) -> None:
        ordering.append("emit:task/failed")

    async def fake_terminate(sandbox_id: str) -> SandboxTerminationResult:
        ordering.append("terminate")
        return SandboxTerminationResult(
            sandbox_id=sandbox_id,
            terminated=True,
            reason=SandboxTerminationReason.TERMINATED,
        )

    monkeypatch.setattr(execute_task_module, "_prepare_execution", fake_prepare)
    monkeypatch.setattr(execute_task_module, "_invoke_sandbox_setup", fake_invoke_sandbox_setup)
    monkeypatch.setattr(execute_task_module, "_invoke_worker_execute", fake_invoke_worker_execute)
    monkeypatch.setattr(execute_task_module, "_invoke_persist_outputs", fake_invoke_persist_outputs)
    monkeypatch.setattr(execute_task_module, "_emit_task_failed", fake_emit_failed)
    monkeypatch.setattr(
        execute_task_module,
        "TaskExecutionService",
        lambda: SimpleNamespace(finalize_success=AsyncMock(), finalize_failure=AsyncMock()),
    )
    monkeypatch.setattr(execute_task_module, "terminate_sandbox_by_id", fake_terminate)

    result = await execute_task_module.run_execute_task_job(
        ctx,
        payload,
        sandbox_setup_function=_FAKE_FN,
        worker_execute_function=_FAKE_FN,
        persist_outputs_function=_FAKE_FN,
        evaluate_task_run_function=_FAKE_FN,
    )
    assert result.success is False
    assert "terminate" in ordering, "sandbox must terminate on the failure path too"


__all__: Sequence[str] = ()
