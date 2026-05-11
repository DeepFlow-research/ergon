"""Contracts for the public WorkerContext runtime facade."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, ClassVar
from uuid import UUID, uuid4

import pytest

from ergon_core.api import (
    Evaluator,
    Sandbox,
    Task,
    Worker,
    WorkerContext,
    WorkerOutput,
)
from ergon_core.core.application.tasks.models import SubtaskInfo


class _Worker(Worker):
    type_slug: ClassVar[str] = "test-worker-context-worker"

    async def execute(self, task: Task, *, context: WorkerContext, sandbox: Sandbox):
        yield WorkerOutput(output="ok")


class _Sandbox(Sandbox):
    async def provision(self) -> None:
        return None


class _Evaluator(Evaluator):
    type_slug: ClassVar[str] = "test-worker-context-evaluator"

    def criteria_for(self, task: Task):
        return ()

    def aggregate_task(self, task: Task, criterion_results):
        raise NotImplementedError


class _SessionFactory:
    def __init__(self) -> None:
        self.sessions: list[object] = []

    @contextmanager
    def __call__(self):
        session = object()
        self.sessions.append(session)
        yield session


class _TaskManagement:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any, Any]] = []

    async def spawn_task(self, session: object, **kwargs: Any) -> Any:
        self.calls.append(("spawn_task", session, kwargs))

        class Result:
            task_id = kwargs["task"]._task_id
            task_slug = kwargs["task"].task_slug
            status = "pending"

        return Result()

    async def cancel_task_by_id(self, session: object, **kwargs: Any) -> None:
        self.calls.append(("cancel_task_by_id", session, kwargs))

    async def refine_task_by_id(self, session: object, **kwargs: Any) -> None:
        self.calls.append(("refine_task_by_id", session, kwargs))

    async def restart_task_by_id(self, session: object, **kwargs: Any) -> None:
        self.calls.append(("restart_task_by_id", session, kwargs))


class _TaskInspection:
    def __init__(self, *, parent_task_id: UUID, child_task_id: UUID) -> None:
        self.parent_task_id = parent_task_id
        self.child_task_id = child_task_id
        self.calls: list[tuple[str, Any, dict[str, Any]]] = []

    def is_descendant(self, session: object, *, run_id: UUID, ancestor_task_id: UUID, candidate_task_id: UUID) -> bool:
        self.calls.append(
            (
                "is_descendant",
                session,
                {
                    "run_id": run_id,
                    "ancestor_task_id": ancestor_task_id,
                    "candidate_task_id": candidate_task_id,
                },
            )
        )
        return ancestor_task_id == self.parent_task_id and candidate_task_id == self.child_task_id

    def list_subtasks(self, session: object, *, run_id: UUID, parent_task_id: UUID) -> list[SubtaskInfo]:
        self.calls.append(("list_subtasks", session, {"run_id": run_id, "parent_task_id": parent_task_id}))
        return []


def _task(*, task_id: UUID) -> Task:
    task = Task(
        task_slug="child",
        instance_key="sample-1",
        description="child task",
        worker=_Worker(name="worker"),
        sandbox=_Sandbox(),
        evaluators=(_Evaluator(name="evaluator"),),
    )
    object.__setattr__(task, "_task_id", task_id)
    return task


@pytest.mark.asyncio
async def test_worker_context_spawns_bound_task_through_internal_service() -> None:
    run_id = uuid4()
    parent_task_id = uuid4()
    child_task_id = uuid4()
    session_factory = _SessionFactory()
    task_mgmt = _TaskManagement()

    context = WorkerContext._for_job(
        run_id=run_id,
        definition_id=uuid4(),
        execution_id=uuid4(),
        task_id=parent_task_id,
        task_mgmt=task_mgmt,
        task_inspect=_TaskInspection(parent_task_id=parent_task_id, child_task_id=child_task_id),
        resource_repo=object(),
        session_factory=session_factory,
    )

    handle = await context.spawn_task(_task(task_id=child_task_id), depends_on=(parent_task_id,))

    assert handle.task_id == child_task_id
    assert handle.task_slug == "child"
    name, session, kwargs = task_mgmt.calls[0]
    assert name == "spawn_task"
    assert session is session_factory.sessions[0]
    assert kwargs["run_id"] == run_id
    assert kwargs["parent_task_id"] == parent_task_id
    assert kwargs["depends_on"] == [parent_task_id]


@pytest.mark.asyncio
async def test_worker_context_checks_containment_before_mutation() -> None:
    run_id = uuid4()
    parent_task_id = uuid4()
    child_task_id = uuid4()
    session_factory = _SessionFactory()
    task_mgmt = _TaskManagement()
    task_inspect = _TaskInspection(parent_task_id=parent_task_id, child_task_id=child_task_id)

    context = WorkerContext._for_job(
        run_id=run_id,
        definition_id=uuid4(),
        execution_id=uuid4(),
        task_id=parent_task_id,
        task_mgmt=task_mgmt,
        task_inspect=task_inspect,
        resource_repo=object(),
        session_factory=session_factory,
    )

    await context.cancel_task(child_task_id)

    assert task_inspect.calls[0][0] == "is_descendant"
    name, session, kwargs = task_mgmt.calls[0]
    assert name == "cancel_task_by_id"
    assert session is session_factory.sessions[1]
    assert kwargs["run_id"] == run_id
    assert kwargs["task_id"] == child_task_id
