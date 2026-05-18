from contextlib import nullcontext
from functools import partial
from types import SimpleNamespace
from uuid import uuid4

import pytest

from ergon_core.core.application.events.task_events import TaskReadyEvent
from ergon_core.core.application.jobs.execute_task import _fan_out_evaluators
from ergon_core.core.application.workflows.orchestration import PreparedTaskExecution


class _FakeStep:
    def __init__(self) -> None:
        self.payloads: list[dict] = []

    async def invoke(self, _name: str, *, function: object, data: dict) -> None:
        del function
        self.payloads.append(data)


class _FakeGroup:
    async def parallel(self, calls: tuple[partial, ...]) -> None:
        for call in calls:
            await call()


class _FakeCtx:
    def __init__(self) -> None:
        self.step = _FakeStep()
        self.group = _FakeGroup()


class _FakeGraphRepo:
    def __init__(self, task: SimpleNamespace) -> None:
        self._task = task

    async def node(self, _session: object, *, run_id, task_id, sandbox_id=None):
        del run_id, task_id, sandbox_id
        return SimpleNamespace(task=self._task)


def _prepared(run_id, definition_id, task_id, execution_id) -> PreparedTaskExecution:
    return PreparedTaskExecution(
        run_id=run_id,
        definition_id=definition_id,
        task_id=task_id,
        task_slug="root",
        task_description="root task",
        benchmark_type="benchmark",
        execution_id=execution_id,
    )


@pytest.mark.asyncio
async def test_fanout_uses_object_bound_evaluator_count(monkeypatch) -> None:
    from ergon_core.core.application.jobs import execute_task as module

    run_id = uuid4()
    definition_id = uuid4()
    task_id = uuid4()
    execution_id = uuid4()
    ctx = _FakeCtx()
    task = SimpleNamespace(
        evaluators=(object(), object()),
        evaluator_binding_keys=(),
    )

    monkeypatch.setattr(module, "get_session", lambda: nullcontext(object()))
    monkeypatch.setattr(module, "WorkflowGraphRepository", lambda: _FakeGraphRepo(task))

    await _fan_out_evaluators(
        ctx,
        TaskReadyEvent(
            run_id=run_id,
            definition_id=definition_id,
            task_id=task_id,
            node_id=task_id,
        ),
        _prepared(run_id, definition_id, task_id, execution_id),
        evaluate_task_run_function=object(),
    )

    assert [payload["evaluator_index"] for payload in ctx.step.payloads] == [0, 1]


@pytest.mark.asyncio
async def test_fanout_uses_legacy_binding_keys_only_as_pr11_bridge(monkeypatch) -> None:
    from ergon_core.core.application.jobs import execute_task as module

    run_id = uuid4()
    definition_id = uuid4()
    task_id = uuid4()
    execution_id = uuid4()
    ctx = _FakeCtx()
    task = SimpleNamespace(
        evaluators=(),
        evaluator_binding_keys=("legacy-a", "legacy-b"),
    )

    monkeypatch.setattr(module, "get_session", lambda: nullcontext(object()))
    monkeypatch.setattr(module, "WorkflowGraphRepository", lambda: _FakeGraphRepo(task))

    await _fan_out_evaluators(
        ctx,
        TaskReadyEvent(
            run_id=run_id,
            definition_id=definition_id,
            task_id=task_id,
            node_id=task_id,
        ),
        _prepared(run_id, definition_id, task_id, execution_id),
        evaluate_task_run_function=object(),
    )

    assert [payload["evaluator_index"] for payload in ctx.step.payloads] == [0, 1]
