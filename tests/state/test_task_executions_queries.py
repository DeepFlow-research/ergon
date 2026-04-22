"""Tests for TaskExecutionsQueries.get_task_payload.

Exercises the JOIN from ``run_task_executions`` → ``experiment_definition_tasks``
that the SWE-Bench sandbox manager uses to read the per-task instance payload.
"""

from contextlib import contextmanager
from uuid import uuid4

import pytest
from ergon_core.core.persistence.definitions.models import (
    ExperimentDefinition,
    ExperimentDefinitionInstance,
    ExperimentDefinitionTask,
)
from ergon_core.core.persistence.queries import queries
from ergon_core.core.persistence.shared.enums import RunStatus, TaskExecutionStatus
from ergon_core.core.persistence.telemetry.models import RunRecord, RunTaskExecution
from sqlmodel import Session


def _patch_get_session(monkeypatch: pytest.MonkeyPatch, session: Session) -> None:
    """Monkeypatch ``get_session`` so query methods use the test transaction."""

    @contextmanager
    def _test_session():
        yield session

    monkeypatch.setattr(
        "ergon_core.core.persistence.queries.get_session",
        _test_session,
    )


def _seed_execution_with_payload(
    session: Session,
    payload: dict[str, object],
) -> tuple[RunTaskExecution, ExperimentDefinitionTask]:
    """Insert minimal rows and return (execution, definition_task)."""
    ed = ExperimentDefinition(
        id=uuid4(),
        benchmark_type="swebench-verified",
    )
    session.add(ed)
    session.flush()

    instance = ExperimentDefinitionInstance(
        id=uuid4(),
        experiment_definition_id=ed.id,
        instance_key="test-instance",
    )
    session.add(instance)
    session.flush()

    edt = ExperimentDefinitionTask(
        id=uuid4(),
        experiment_definition_id=ed.id,
        instance_id=instance.id,
        task_slug="test-task",
        description="fixture",
        task_payload=payload,
    )
    run = RunRecord(
        id=uuid4(),
        experiment_definition_id=ed.id,
        status=RunStatus.PENDING,
    )
    session.add_all([edt, run])
    session.flush()

    exe = RunTaskExecution(
        id=uuid4(),
        run_id=run.id,
        definition_task_id=edt.id,
        attempt_number=1,
        status=TaskExecutionStatus.PENDING,
    )
    session.add(exe)
    session.flush()
    return exe, edt


def test_get_task_payload_returns_joined_payload(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_get_session(monkeypatch, session)
    payload = {"instance_id": "django__django-12345", "repo": "django/django"}
    exe, _ = _seed_execution_with_payload(session, payload)

    result = queries.task_executions.get_task_payload(exe.id)
    assert result == payload


def test_get_task_payload_returns_none_for_missing_execution(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_get_session(monkeypatch, session)
    assert queries.task_executions.get_task_payload(uuid4()) is None
