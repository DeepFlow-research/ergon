from collections.abc import Iterable, Iterator
from importlib import import_module
from uuid import uuid4

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from ergon_core.api import Sample
from ergon_core.api.benchmark import Task
from ergon_core.api.criterion.outcome import CriterionOutcome
from ergon_core.api.rubric.evaluator import Evaluator
from ergon_core.api.rubric.results import TaskEvaluationResult
from ergon_core.core.application.events.runtime import TaskCancelledEvent, WorkflowStartedEvent
from ergon_core.core.application.runtime.lifecycle import get_initial_ready_tasks
from ergon_core.core.application.runtime.orchestration import (
    InitializeWorkflowCommand,
    PrepareTaskExecutionCommand,
)
from ergon_core.core.application.runtime.sample_lifecycle import WorkflowService
from ergon_core.core.application.samples.materialization import materialize_sample
from ergon_core.core.jobs.resources.persist_outputs.contract import PersistOutputsRequest
from ergon_core.core.jobs.sandbox.setup.contract import SandboxSetupRequest
from ergon_core.core.jobs.task.worker_execute.contract import WorkerExecuteRequest
from ergon_core.core.jobs.workflow.start.job import run_workflow_start_job
from ergon_core.core.persistence.graph.models import SampleGraphNode
from ergon_core.core.persistence.samples.models import SampleStatusEventRow, SampleTaskEventRow
from ergon_core.core.persistence.shared.enums import SampleStatus
from ergon_core.core.persistence.telemetry.models import SampleRecord
from ergon_core.test_support.task_factory import task_with_id

for module_name in (
    "ergon_core.core.persistence.definitions.models",
    "ergon_core.core.persistence.experiments.models",
    "ergon_core.core.persistence.graph.models",
    "ergon_core.core.persistence.samples.models",
    "ergon_core.core.persistence.telemetry.models",
):
    import_module(module_name)


class StartPathEvaluator(Evaluator):
    type_slug = "start-test-evaluator"

    def criteria_for(self, task: Task) -> Iterable:
        return ()

    def aggregate_task(
        self,
        task: Task,
        criterion_results: Iterable[CriterionOutcome],
    ) -> TaskEvaluationResult:
        return TaskEvaluationResult(
            task_slug=task.task_slug,
            score=1.0,
            passed=True,
            evaluator_name=self.name,
            criterion_results=list(criterion_results),
        )


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture()
def materialized_sample(session: Session) -> SampleRecord:
    root = task_with_id(
        uuid4(),
        task_slug="root",
        instance_key="a",
        description="Root task",
        evaluators=(StartPathEvaluator(name="judge"),),
    )
    child = task_with_id(
        uuid4(),
        task_slug="child",
        instance_key="a",
        description="Child task",
        dependency_task_slugs=("root",),
    )
    sample = Sample.from_tasks(
        name="mini:a",
        sample_key="a",
        environment_name="mini",
        tasks=[root, child],
    )
    sample_row = SampleRecord(
        benchmark_type="experiment",
        instance_key="a",
        status=SampleStatus.PENDING,
    )
    session.add(sample_row)
    session.flush()
    materialize_sample(session=session, sample=sample, sample_row=sample_row)
    session.commit()
    return sample_row


@pytest.mark.asyncio
async def test_workflow_start_uses_materialized_sample_graph_without_definition(
    session: Session,
    materialized_sample: SampleRecord,
) -> None:
    result = await run_workflow_start_job(
        session=session,
        event=WorkflowStartedEvent(sample_id=materialized_sample.id),
    )
    assert result.initial_ready_tasks == 1

    ready = await get_initial_ready_tasks(
        session=session,
        sample_id=materialized_sample.id,
        definition_id=None,
    )

    nodes_by_id = {
        node.task_id: node
        for node in session.exec(
            select(SampleGraphNode).where(SampleGraphNode.sample_id == materialized_sample.id)
        )
    }
    assert ready == []
    assert [node.task_slug for node in nodes_by_id.values() if node.status == "ready"] == ["root"]


def test_sample_only_task_execution_contracts_allow_missing_definition_id() -> None:
    sample_id = uuid4()
    task_id = uuid4()
    execution_id = uuid4()

    assert PrepareTaskExecutionCommand(sample_id=sample_id, task_id=task_id).definition_id is None
    assert (
        SandboxSetupRequest(
            sample_id=sample_id,
            task_id=task_id,
            benchmark_type="experiment",
        ).definition_id
        is None
    )
    assert (
        WorkerExecuteRequest(
            sample_id=sample_id,
            task_id=task_id,
            execution_id=execution_id,
            sandbox_id="sandbox",
            task_slug="root",
            task_description="Root task",
            assigned_worker_slug="worker",
            worker_type="worker.Type",
            benchmark_type="experiment",
        ).definition_id
        is None
    )
    assert (
        PersistOutputsRequest(
            sample_id=sample_id,
            task_id=task_id,
            execution_id=execution_id,
            benchmark_type="experiment",
        ).definition_id
        is None
    )
    assert (
        TaskCancelledEvent(
            sample_id=sample_id,
            task_id=task_id,
            execution_id=None,
            cause="manager_decision",
        ).definition_id
        is None
    )


@pytest.mark.asyncio
async def test_materialized_workflow_start_is_idempotent(
    session: Session,
    materialized_sample: SampleRecord,
) -> None:
    service = WorkflowService()

    first = await service.initialize(
        InitializeWorkflowCommand(sample_id=materialized_sample.id),
        session=session,
    )
    first_ready_ids = [task.task_id for task in first.initial_ready_tasks]
    assert first_ready_ids
    root_id = first_ready_ids[0]
    root = session.get(SampleGraphNode, (materialized_sample.id, root_id))
    assert root is not None
    root.status = "running"
    session.add(root)
    session.commit()

    second = await service.initialize(
        InitializeWorkflowCommand(sample_id=materialized_sample.id),
        session=session,
    )

    assert second.initial_ready_tasks == []
    assert second.total_root_tasks == first.total_root_tasks == 1
    root_after_retry = session.get(SampleGraphNode, (materialized_sample.id, root_id))
    assert root_after_retry is not None
    assert root_after_retry.status == "running"
    assert (
        len(
            session.exec(
                select(SampleStatusEventRow)
                .where(SampleStatusEventRow.sample_id == materialized_sample.id)
                .where(SampleStatusEventRow.status == SampleStatus.EXECUTING)
            ).all()
        )
        == 1
    )
    task_events = session.exec(
        select(SampleTaskEventRow)
        .where(SampleTaskEventRow.sample_id == materialized_sample.id)
        .where(SampleTaskEventRow.task_id == root_id)
        .where(SampleTaskEventRow.event_type == "task.status_changed")
    ).all()
    assert len(task_events) == 1


@pytest.mark.asyncio
async def test_materialized_workflow_start_retry_before_worker_claim_is_idempotent(
    session: Session,
    materialized_sample: SampleRecord,
) -> None:
    service = WorkflowService()

    first = await service.initialize(
        InitializeWorkflowCommand(sample_id=materialized_sample.id),
        session=session,
    )
    first_ready_ids = [task.task_id for task in first.initial_ready_tasks]
    assert first_ready_ids

    second = await service.initialize(
        InitializeWorkflowCommand(sample_id=materialized_sample.id),
        session=session,
    )

    assert second.initial_ready_tasks == []
    assert second.total_root_tasks == first.total_root_tasks == 1
    task_events = session.exec(
        select(SampleTaskEventRow)
        .where(SampleTaskEventRow.sample_id == materialized_sample.id)
        .where(SampleTaskEventRow.task_id == first_ready_ids[0])
        .where(SampleTaskEventRow.event_type == "task.status_changed")
    ).all()
    assert len(task_events) == 1
    assert task_events[0].status == "ready"
