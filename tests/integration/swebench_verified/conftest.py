"""Shared fixtures for swebench_verified integration tests."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from ergon_core.core.persistence.definitions.models import (
    ExperimentDefinition,
    ExperimentDefinitionInstance,
    ExperimentDefinitionTask,
)
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.shared.enums import RunStatus, TaskExecutionStatus
from ergon_core.core.persistence.telemetry.models import (
    ExperimentRecord,
    RunRecord,
    RunTaskExecution,
)
from sqlmodel import select

_MINIMAL_SWEBENCH_PAYLOAD: dict[str, object] = {
    "instance_id": "django__django-1",
    "repo": "django/django",
    "base_commit": "aaa000",
    "version": "3.0",
    "problem_statement": "fix it",
    "hints_text": "",
    "fail_to_pass": ["tests.test_app.TestCase.test_method"],
    "pass_to_pass": [],
    "environment_setup_commit": "aaa000",
    "test_patch": "",
}


@pytest.fixture()
def swebench_execution() -> tuple[UUID, UUID]:
    """Seed the minimal FK chain needed by SWEBenchSandboxManager._install_dependencies.

    Seeds: ExperimentDefinition → ExperimentDefinitionInstance →
    ExperimentDefinitionTask + RunRecord → RunTaskExecution(id=execution_id).

    Yields (execution_id, run_id) so tests can pass execution_id as
    sandbox_key and run_id as run_id to mgr.create().

    Cleans up all seeded rows after the test.
    """
    execution_id = uuid4()

    with get_session() as session:
        defn = ExperimentDefinition(benchmark_type="swebench-verified")
        session.add(defn)
        session.flush()
        session.refresh(defn)

        instance = ExperimentDefinitionInstance(
            experiment_definition_id=defn.id,
            instance_key="django__django-1",
        )
        session.add(instance)
        session.flush()
        session.refresh(instance)

        task = ExperimentDefinitionTask(
            experiment_definition_id=defn.id,
            instance_id=instance.id,
            task_slug="django__django-1",
            description="swebench sandbox manager test task",
            task_payload_json=dict(_MINIMAL_SWEBENCH_PAYLOAD),
        )
        session.add(task)
        session.flush()
        session.refresh(task)

        experiment = ExperimentRecord(
            name="swebench verified fixture",
            benchmark_type="swebench-verified",
            sample_count=1,
            sample_selection_json={"instance_keys": ["django__django-1"]},
            default_worker_team_json={"primary": "swebench-verified"},
            design_json={},
            metadata_json={},
            status="running",
        )
        session.add(experiment)
        session.flush()
        session.refresh(experiment)

        run = RunRecord(
            experiment_id=experiment.id,
            workflow_definition_id=defn.id,
            benchmark_type="swebench-verified",
            instance_key="django__django-1",
            worker_team_json={"primary": "swebench-verified"},
            status=RunStatus.EXECUTING,
        )
        session.add(run)
        session.flush()
        session.refresh(run)

        execution = RunTaskExecution(
            id=execution_id,
            run_id=run.id,
            definition_task_id=task.id,
            status=TaskExecutionStatus.RUNNING,
        )
        session.add(execution)
        session.commit()

        run_id: UUID = run.id
        defn_id: UUID = defn.id

    yield execution_id, run_id

    with get_session() as session:
        exec_row = session.get(RunTaskExecution, execution_id)
        if exec_row is not None:
            session.delete(exec_row)
        run_row = session.get(RunRecord, run_id)
        if run_row is not None:
            session.delete(run_row)
        for t in session.exec(
            select(ExperimentDefinitionTask).where(
                ExperimentDefinitionTask.experiment_definition_id == defn_id
            )
        ).all():
            session.delete(t)
        for inst in session.exec(
            select(ExperimentDefinitionInstance).where(
                ExperimentDefinitionInstance.experiment_definition_id == defn_id
            )
        ).all():
            session.delete(inst)
        defn_row = session.get(ExperimentDefinition, defn_id)
        if defn_row is not None:
            session.delete(defn_row)
        session.commit()
