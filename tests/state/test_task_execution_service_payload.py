"""State-level coverage: TaskExecutionService.prepare() must surface
`ExperimentDefinitionTask.task_payload` on the returned PreparedTaskExecution.

Regression for the P0 bug documented at
`docs/bugs/open/2026-04-21-task-payload-metadata-propagation.md`: the CLI
composition layer writes keys like `toolkit_benchmark` into
`ExperimentDefinitionTask.task_payload`, and downstream workers require
them via `WorkerContext.metadata`. Prior to the fix, `prepare()` silently
dropped the payload between DB and DTO.
"""

from contextlib import contextmanager

import pytest
from ergon_core.core.persistence.definitions.models import (
    ExperimentDefinitionTask,
    ExperimentDefinitionTaskAssignment,
    ExperimentDefinitionWorker,
)
from ergon_core.core.persistence.graph.models import RunGraphNode
from ergon_core.core.runtime.services.orchestration_dto import (
    PrepareTaskExecutionCommand,
)
from ergon_core.core.runtime.services.task_execution_service import (
    TaskExecutionService,
)
from sqlmodel import Session

from tests.state.factories import seed_flat_tasks, seed_run


def _patch_get_session(monkeypatch: pytest.MonkeyPatch, session: Session) -> None:
    @contextmanager
    def _test_session():
        yield session

    monkeypatch.setattr(
        "ergon_core.core.runtime.services.task_execution_service.get_session",
        _test_session,
    )


class TestPrepareDefinitionPropagatesTaskPayload:
    async def test_task_payload_flows_to_prepared_execution(
        self, session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def_id, _, task_ids = seed_flat_tasks(session, 1)
        run_id = seed_run(session, def_id)

        # Backfill the task row with a realistic composed payload.
        task_row = session.get(ExperimentDefinitionTask, task_ids[0])
        assert task_row is not None
        task_row.task_payload = {"toolkit_benchmark": "minif2f"}
        session.add(task_row)

        # Worker binding so prepare() completes without ConfigurationError.
        worker = ExperimentDefinitionWorker(
            experiment_definition_id=def_id,
            binding_key="researcher",
            worker_type="cloud-llm",
            model_target="gpt-4o",
        )
        session.add(worker)
        session.add(
            ExperimentDefinitionTaskAssignment(
                experiment_definition_id=def_id,
                task_id=task_ids[0],
                worker_binding_key="researcher",
            )
        )
        # Graph node so GraphNodeLookup can resolve.
        session.add(
            RunGraphNode(
                run_id=run_id,
                definition_task_id=task_ids[0],
                instance_key="inst-0",
                task_slug="task-0",
                description="Test task 0",
                status="pending",
                assigned_worker_slug="researcher",
            )
        )
        session.flush()

        _patch_get_session(monkeypatch, session)
        svc = TaskExecutionService()

        result = await svc.prepare(
            PrepareTaskExecutionCommand(
                run_id=run_id,
                definition_id=def_id,
                task_id=task_ids[0],
            )
        )

        assert result.task_payload == {"toolkit_benchmark": "minif2f"}

    async def test_empty_task_payload_remains_empty(
        self, session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def_id, _, task_ids = seed_flat_tasks(session, 1)
        run_id = seed_run(session, def_id)

        worker = ExperimentDefinitionWorker(
            experiment_definition_id=def_id,
            binding_key="researcher",
            worker_type="cloud-llm",
            model_target="gpt-4o",
        )
        session.add(worker)
        session.add(
            ExperimentDefinitionTaskAssignment(
                experiment_definition_id=def_id,
                task_id=task_ids[0],
                worker_binding_key="researcher",
            )
        )
        session.add(
            RunGraphNode(
                run_id=run_id,
                definition_task_id=task_ids[0],
                instance_key="inst-0",
                task_slug="task-0",
                description="Test task 0",
                status="pending",
                assigned_worker_slug="researcher",
            )
        )
        session.flush()

        _patch_get_session(monkeypatch, session)
        svc = TaskExecutionService()

        result = await svc.prepare(
            PrepareTaskExecutionCommand(
                run_id=run_id,
                definition_id=def_id,
                task_id=task_ids[0],
            )
        )

        assert result.task_payload == {}
