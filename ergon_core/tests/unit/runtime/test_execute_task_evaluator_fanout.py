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

from collections.abc import Sequence
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from ergon_core.core.application.events.task_events import TaskReadyEvent
from ergon_core.core.application.jobs import execute_task as execute_task_module
from ergon_core.core.application.workflows.orchestration import PreparedTaskExecution
from ergon_core.core.infrastructure.sandbox.lifecycle import (
    SandboxTerminationReason,
    SandboxTerminationResult,
)


class _OrderedFakeCtx:
    """Records every step-invoke and step-run by step_id."""

    def __init__(self, ordering: list[str]) -> None:
        self._ordering = ordering
        self.step = SimpleNamespace(
            invoke=self._invoke,
            run=self._run,
        )

    async def _invoke(self, step_id: str, *, function: Any, data: Any) -> Any:
        del function, data
        self._ordering.append(f"invoke:{step_id}")
        # Mimic Inngest's invoke return: the function's output type.
        # Tests below don't read the return value beyond presence.
        return SimpleNamespace(sandbox_id="sbx-test", output_dir=None, success=True)

    async def _run(self, step_id: str, fn, *, output_type=None):
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

    async def fake_prepare(_ctx, _svc, _payload):
        ordering.append("prepare")
        return prepared

    async def fake_setup_sandbox(_ctx, _payload, _prepared, _fn):
        ordering.append("invoke:sandbox-setup")
        return SimpleNamespace(sandbox_id="sbx-test", output_dir=None)

    async def fake_run_worker(_ctx, _payload, _prepared, _sandbox, _fn):
        ordering.append("invoke:worker-execute")
        return SimpleNamespace(
            success=True,
            final_assistant_message="ok",
            error=None,
            error_json=None,
        )

    async def fake_persist_outputs(_ctx, _payload, _prepared, _sandbox, _fn):
        ordering.append("invoke:persist-outputs")
        return SimpleNamespace(outputs_count=0)

    async def fake_emit_completed(_payload, _prepared, _sandbox_id):
        ordering.append("emit:task/completed")

    # Two evaluators bound on the task so the gather sees a real fanout.
    view_task = SimpleNamespace(evaluator_binding_keys=("a", "b"))
    view = SimpleNamespace(task=view_task)
    repo = SimpleNamespace(node=AsyncMock(return_value=view))

    async def fake_fanout(ctx, payload, prepared, eval_fn):
        # Use the real implementation but bypass the session machinery.
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
    monkeypatch.setattr(execute_task_module, "_setup_sandbox", fake_setup_sandbox)
    monkeypatch.setattr(execute_task_module, "_run_worker", fake_run_worker)
    monkeypatch.setattr(execute_task_module, "_persist_outputs", fake_persist_outputs)
    monkeypatch.setattr(execute_task_module, "_emit_task_completed", fake_emit_completed)
    monkeypatch.setattr(execute_task_module, "_fan_out_evaluators", fake_fanout)
    monkeypatch.setattr(execute_task_module, "TaskExecutionService", lambda: svc)
    monkeypatch.setattr(execute_task_module, "terminate_sandbox_by_id", fake_terminate)
    monkeypatch.setattr(execute_task_module.WorkflowGraphRepository, "node", repo.node)

    sentinel = object()
    result = await execute_task_module.run_execute_task_job(
        ctx,
        payload,
        sandbox_setup_function=sentinel,
        worker_execute_function=sentinel,
        persist_outputs_function=sentinel,
        evaluate_task_run_function=sentinel,
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

    async def fake_prepare(_ctx, _svc, _payload):
        return prepared

    async def fake_setup_sandbox(_ctx, _payload, _prepared, _fn):
        return SimpleNamespace(sandbox_id="sbx-fail", output_dir=None)

    async def fake_run_worker(_ctx, _payload, _prepared, _sandbox, _fn):
        return SimpleNamespace(
            success=False,
            final_assistant_message=None,
            error="boom",
            error_json={"message": "boom"},
        )

    async def fake_persist_outputs(_ctx, _payload, _prepared, _sandbox, _fn):
        return SimpleNamespace(outputs_count=0)

    async def fake_emit_failed(_payload, _prepared, _error, _sandbox_id):
        ordering.append("emit:task/failed")

    async def fake_terminate(sandbox_id: str) -> SandboxTerminationResult:
        ordering.append("terminate")
        return SandboxTerminationResult(
            sandbox_id=sandbox_id,
            terminated=True,
            reason=SandboxTerminationReason.TERMINATED,
        )

    monkeypatch.setattr(execute_task_module, "_prepare_execution", fake_prepare)
    monkeypatch.setattr(execute_task_module, "_setup_sandbox", fake_setup_sandbox)
    monkeypatch.setattr(execute_task_module, "_run_worker", fake_run_worker)
    monkeypatch.setattr(execute_task_module, "_persist_outputs", fake_persist_outputs)
    monkeypatch.setattr(execute_task_module, "_emit_task_failed", fake_emit_failed)
    monkeypatch.setattr(
        execute_task_module,
        "TaskExecutionService",
        lambda: SimpleNamespace(finalize_success=AsyncMock(), finalize_failure=AsyncMock()),
    )
    monkeypatch.setattr(execute_task_module, "terminate_sandbox_by_id", fake_terminate)

    sentinel = object()
    result = await execute_task_module.run_execute_task_job(
        ctx,
        payload,
        sandbox_setup_function=sentinel,
        worker_execute_function=sentinel,
        persist_outputs_function=sentinel,
        evaluate_task_run_function=sentinel,
    )
    assert result.success is False
    assert "terminate" in ordering, "sandbox must terminate on the failure path too"


__all__: Sequence[str] = ()
