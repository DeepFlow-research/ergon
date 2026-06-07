from contextlib import nullcontext
from functools import partial
from types import SimpleNamespace
from uuid import uuid4

import pytest

from ergon_core.core.jobs.task.execute.contract import TaskReadyEvent
from ergon_core.core.jobs.task.execute.job import _fan_out_evaluators
from ergon_core.core.application.runtime.orchestration import PreparedTaskExecution


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


class _FakeTaskExecutionService:
    def __init__(self, task: SimpleNamespace) -> None:
        self._task = task

    async def load_task_view(self, _session: object, *, sample_id, task_id, sandbox_id=None):
        del sample_id, task_id, sandbox_id
        return SimpleNamespace(task=self._task)


def _prepared(sample_id, definition_id, task_id, execution_id) -> PreparedTaskExecution:
    return PreparedTaskExecution(
        sample_id=sample_id,
        definition_id=definition_id,
        task_id=task_id,
        task_slug="root",
        task_description="root task",
        benchmark_type="benchmark",
        execution_id=execution_id,
    )


@pytest.mark.asyncio
async def test_fanout_uses_object_bound_evaluator_count(monkeypatch) -> None:
    sample_id = uuid4()
    definition_id = uuid4()
    task_id = uuid4()
    execution_id = uuid4()
    ctx = _FakeCtx()
    task = SimpleNamespace(
        evaluators=(object(), object()),
    )

    from ergon_core.core.jobs.task.execute import job as module

    monkeypatch.setattr(module, "get_session", lambda: nullcontext(object()))

    await _fan_out_evaluators(
        ctx,
        _FakeTaskExecutionService(task),
        TaskReadyEvent(
            sample_id=sample_id,
            definition_id=definition_id,
            task_id=task_id,
        ),
        _prepared(sample_id, definition_id, task_id, execution_id),
        evaluate_task_run_function=object(),
    )

    assert [payload["evaluator_index"] for payload in ctx.step.payloads] == [0, 1]


@pytest.mark.asyncio
async def test_fanout_emits_no_jobs_without_inline_evaluators(monkeypatch) -> None:
    sample_id = uuid4()
    definition_id = uuid4()
    task_id = uuid4()
    execution_id = uuid4()
    ctx = _FakeCtx()
    task = SimpleNamespace(
        evaluators=(),
    )

    from ergon_core.core.jobs.task.execute import job as module

    monkeypatch.setattr(module, "get_session", lambda: nullcontext(object()))

    await _fan_out_evaluators(
        ctx,
        _FakeTaskExecutionService(task),
        TaskReadyEvent(
            sample_id=sample_id,
            definition_id=definition_id,
            task_id=task_id,
        ),
        _prepared(sample_id, definition_id, task_id, execution_id),
        evaluate_task_run_function=object(),
    )

    assert ctx.step.payloads == []
