from collections.abc import Iterable, Iterator
from importlib import import_module
from uuid import uuid4

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from ergon_core.api import Sample
from ergon_core.api.task import Task
from ergon_core.api.criterion.outcome import CriterionOutcome
from ergon_core.api.rubric.evaluator import Evaluator
from ergon_core.api.rubric.results import TaskEvaluationResult
from ergon_core.core.application.samples.materialization import materialize_sample
from ergon_core.core.persistence.graph.models import SampleGraphEdge, SampleGraphNode
from ergon_core.core.persistence.samples.models import (
    SampleEvaluatorEventRow,
    SampleSandboxEventRow,
    SampleTaskEventRow,
    SampleWorkerEventRow,
)
from ergon_core.core.persistence.shared.enums import SampleStatus
from ergon_core.core.persistence.telemetry.models import SampleRecord
from ergon_core.test_support.task_factory import task_with_id

for module_name in (
    "ergon_core.core.persistence.experiments.models",
    "ergon_core.core.persistence.graph.models",
    "ergon_core.core.persistence.samples.models",
    "ergon_core.core.persistence.telemetry.models",
):
    import_module(module_name)


class MaterializationEvaluator(Evaluator):
    type_slug = "test-evaluator"

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
def selected_sample() -> Sample:
    root = task_with_id(
        uuid4(),
        task_slug="root",
        instance_key="a",
        description="Root task",
        evaluators=(MaterializationEvaluator(name="judge"),),
    )
    child = task_with_id(
        uuid4(),
        task_slug="child",
        instance_key="a",
        description="Child task",
        dependency_task_slugs=("root",),
    )
    return Sample.from_tasks(
        name="mini:a",
        sample_key="a",
        environment_name="mini",
        tasks=[root, child],
        sample_ref={"key": "a"},
    )


@pytest.fixture()
def sample_row(session: Session) -> SampleRecord:
    row = SampleRecord(
        benchmark_type="experiment",
        instance_key="a",
        status=SampleStatus.PENDING,
    )
    session.add(row)
    session.flush()
    return row


def test_materialization_persists_task_json_not_environment_or_experiment(
    session: Session,
    selected_sample: Sample,
    sample_row: SampleRecord,
) -> None:
    materialize_sample(session=session, sample=selected_sample, sample_row=sample_row)

    node = session.exec(
        select(SampleGraphNode).where(SampleGraphNode.sample_id == sample_row.id)
    ).first()
    task_event = session.exec(
        select(SampleTaskEventRow).where(SampleTaskEventRow.sample_id == sample_row.id)
    ).first()
    worker_event = session.exec(
        select(SampleWorkerEventRow).where(SampleWorkerEventRow.sample_id == sample_row.id)
    ).first()
    evaluator_event = session.exec(
        select(SampleEvaluatorEventRow).where(SampleEvaluatorEventRow.sample_id == sample_row.id)
    ).first()
    sandbox_event = session.exec(
        select(SampleSandboxEventRow).where(SampleSandboxEventRow.sample_id == sample_row.id)
    ).first()

    assert node is not None
    assert task_event is not None
    assert worker_event is not None
    assert evaluator_event is not None
    assert sandbox_event is not None
    assert node.task_json["_type"]
    assert node.task_json["worker"]["_type"]
    assert node.task_json["sandbox"]["_type"]
    assert node.task_json["evaluators"][0]["_type"]
    assert task_event.task_snapshot_json == node.task_json
    assert worker_event.worker_slug == "test-worker"
    assert worker_event.worker_type == node.task_json["worker"]["_type"]
    assert worker_event.model_target == "test:none"
    assert worker_event.worker_snapshot_json == node.task_json["worker"]
    assert evaluator_event.evaluator_slug == "judge"
    assert evaluator_event.evaluator_type == node.task_json["evaluators"][0]["_type"]
    assert evaluator_event.evaluator_snapshot_json == node.task_json["evaluators"][0]
    assert sandbox_event.sandbox_slug == "TestSandbox"
    assert sandbox_event.sandbox_type == node.task_json["sandbox"]["_type"]
    assert sandbox_event.sandbox_snapshot_json == node.task_json["sandbox"]
    assert "environment" not in node.task_json
    assert "experiment" not in node.task_json


def test_materialization_writes_graph_edges_from_task_dependencies(
    session: Session,
    selected_sample: Sample,
    sample_row: SampleRecord,
) -> None:
    materialize_sample(session=session, sample=selected_sample, sample_row=sample_row)

    nodes = session.exec(select(SampleGraphNode)).all()
    edges = session.exec(select(SampleGraphEdge)).all()

    assert {node.task_slug for node in nodes} == {"root", "child"}
    assert len(edges) == 1
