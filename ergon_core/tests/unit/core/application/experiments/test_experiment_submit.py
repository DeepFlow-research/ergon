from collections.abc import Iterator, Sequence
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace
from typing import Literal
from uuid import uuid4

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from ergon_core.api import Environment, Experiment, RandomSampler, Sample
from ergon_core.api.experiment.sampling import SamplingContext
from ergon_core.core.application.events.runtime import WorkflowStartedEvent
from ergon_core.core.application.experiments.submission import (
    ExperimentSubmissionService,
    InngestWorkflowEventBus,
)
from ergon_core.core.persistence.experiments.models import ExperimentSamplePoolEntryRow
from ergon_core.core.persistence.graph.models import SampleGraphNode
from ergon_core.core.persistence.samples.models import SampleEdgeEventRow, SampleTaskEventRow
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


class FakeEventBus:
    def __init__(self) -> None:
        self.events: list[SimpleNamespace] = []

    async def publish(self, event: object) -> None:
        name = getattr(event, "name")
        payload = event.model_dump(mode="json")
        self.events.append(SimpleNamespace(name=name, payload=payload))


class CommittedStateEventBus:
    def __init__(self, engine) -> None:
        self._engine = engine
        self.events: list[WorkflowStartedEvent] = []

    async def publish(self, event: WorkflowStartedEvent) -> None:
        with Session(self._engine) as observer:
            assert observer.get(SampleRecord, event.sample_id) is not None
            assert observer.exec(
                select(SampleGraphNode).where(SampleGraphNode.sample_id == event.sample_id)
            ).first()
            assert observer.exec(
                select(SampleTaskEventRow).where(SampleTaskEventRow.sample_id == event.sample_id)
            ).first()
        self.events.append(event)


class SequentialSampler:
    name = "sequential"

    def config(self) -> dict:
        return {}

    async def select(
        self,
        *,
        samples: Sequence[Sample],
        k: int,
        context: SamplingContext,
    ) -> Sequence[Sample]:
        return list(samples)[:k]


def make_task(task_slug: str, key: str, dependencies: tuple[str, ...] = ()):
    return task_with_id(
        uuid4(),
        task_slug=task_slug,
        instance_key=key,
        description=f"Solve {key}",
        dependency_task_slugs=dependencies,
    )


def make_sample(environment_name: str, key: str) -> Sample:
    return Sample.from_tasks(
        name=f"{environment_name}:{key}",
        sample_key=key,
        environment_name=environment_name,
        tasks=[
            make_task("root", key),
            make_task("child", key, ("root",)),
        ],
        sample_ref={"key": key},
        source_metadata={"source": environment_name},
        metadata={"difficulty": "small"},
    )


class StreamingEnvironment(Environment):
    source_mode: Literal["streaming"] = "streaming"
    total: int

    def iter_samples(self) -> Iterator[Sample]:
        for index in range(self.total):
            yield make_sample(self.name, str(index))


class MaterializedEnvironment(Environment):
    source_mode: Literal["materialized"] = "materialized"
    keys: tuple[str, ...]

    def iter_samples(self) -> Iterator[Sample]:
        for key in self.keys:
            yield make_sample(self.name, key)


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture()
def experiment() -> Experiment:
    return Experiment(
        name="submit smoke",
        environments=[MaterializedEnvironment(name="mini-validation", keys=("a", "b", "c"))],
    )


@pytest.fixture()
def streaming_experiment() -> Experiment:
    return Experiment(
        name="streaming submit",
        environments=[StreamingEnvironment(name="stream", total=20)],
    )


@pytest.fixture()
def two_env_experiment() -> Experiment:
    return Experiment(
        name="two env submit",
        environments=[
            MaterializedEnvironment(name="mini-validation", keys=("a", "b")),
            MaterializedEnvironment(name="swe-validation", keys=("1", "2")),
        ],
    )


@pytest.mark.asyncio
async def test_submit_selects_and_materializes_k_samples(
    session: Session,
    experiment: Experiment,
) -> None:
    service = ExperimentSubmissionService(session=session, event_bus=FakeEventBus())

    result = await experiment.submit(service=service, k=3, sampler=SequentialSampler())

    assert result.selected_count == 3
    assert len(result.sample_ids) == 3
    assert not hasattr(result, "run_ids")
    assert session.exec(select(SampleRecord)).all()
    assert session.exec(
        select(SampleTaskEventRow).where(SampleTaskEventRow.event_type == "task.added")
    ).all()
    assert session.exec(
        select(SampleEdgeEventRow).where(SampleEdgeEventRow.event_type == "edge.added")
    ).all()


@pytest.mark.asyncio
async def test_submit_retains_unselected_candidate_pool_entries(
    session: Session,
    streaming_experiment: Experiment,
) -> None:
    service = ExperimentSubmissionService(session=session, event_bus=FakeEventBus())

    result = await streaming_experiment.submit(
        service=service,
        k=2,
        sampler=SequentialSampler(),
        candidate_pool_size=8,
    )

    rows = session.exec(select(ExperimentSamplePoolEntryRow)).all()
    assert result.selected_count == 2
    assert len(rows) == 8
    assert sum(row.selected for row in rows) == 2


@pytest.mark.asyncio
async def test_submit_caps_random_sampler_selection_to_requested_k(
    session: Session,
    streaming_experiment: Experiment,
) -> None:
    service = ExperimentSubmissionService(session=session, event_bus=FakeEventBus())

    result = await streaming_experiment.submit(
        service=service,
        k=2,
        sampler=RandomSampler(seed=7),
        candidate_pool_size=8,
    )

    pool_rows = session.exec(select(ExperimentSamplePoolEntryRow)).all()
    sample_rows = session.exec(select(SampleRecord)).all()
    assert result.selected_count == 2
    assert len(result.sample_ids) == 2
    assert len(pool_rows) == 8
    assert sum(row.selected for row in pool_rows) == 2
    assert len(sample_rows) == 2


@pytest.mark.asyncio
async def test_submit_records_selected_sample_provenance(
    session: Session,
    two_env_experiment: Experiment,
) -> None:
    service = ExperimentSubmissionService(session=session, event_bus=FakeEventBus())

    result = await two_env_experiment.submit(service=service, k=2, sampler=SequentialSampler())

    sample_rows = session.exec(select(SampleRecord).order_by(SampleRecord.created_at)).all()
    assert [row.id for row in sample_rows] == list(result.sample_ids)
    assert {row.experiment_id for row in sample_rows} == {result.experiment_ref_id}
    assert all(row.environment_id for row in sample_rows)
    assert all(row.pool_entry_id for row in sample_rows)
    assert all(row.sampler_invocation_id == result.sampler_invocation_id for row in sample_rows)
    assert all(row.sample_key for row in sample_rows)
    assert all(isinstance(row.sample_ref_json, dict) for row in sample_rows)


@pytest.mark.asyncio
async def test_submit_emits_sample_start_events_without_definition_or_run_ids(
    session: Session,
    experiment: Experiment,
) -> None:
    event_bus = FakeEventBus()
    service = ExperimentSubmissionService(session=session, event_bus=event_bus)

    result = await experiment.submit(service=service, k=1, sampler=SequentialSampler())

    assert event_bus.events
    assert event_bus.events[0].payload["sample_id"] == str(result.sample_ids[0])
    assert "definition_id" not in event_bus.events[0].payload
    assert "run_id" not in event_bus.events[0].payload


@pytest.mark.asyncio
async def test_submit_commits_materialized_sample_before_start_event(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'submit.db'}")
    SQLModel.metadata.create_all(engine)
    event_bus = CommittedStateEventBus(engine)

    with Session(engine) as session:
        experiment = Experiment(
            name="submit commit boundary",
            environments=[MaterializedEnvironment(name="mini-validation", keys=("a",))],
        )
        service = ExperimentSubmissionService(session=session, event_bus=event_bus)

        result = await experiment.submit(service=service, k=1, sampler=SequentialSampler())

    assert [event.sample_id for event in event_bus.events] == list(result.sample_ids)


@pytest.mark.asyncio
async def test_default_event_bus_sends_workflow_started(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[object] = []

    async def fake_send(event: object) -> None:
        sent.append(event)

    monkeypatch.setattr(
        "ergon_core.core.application.experiments.submission.inngest_client.send",
        fake_send,
    )
    event = WorkflowStartedEvent(sample_id=uuid4())

    await InngestWorkflowEventBus().publish(event)

    assert len(sent) == 1
    assert getattr(sent[0], "name") == WorkflowStartedEvent.name
    assert getattr(sent[0], "data") == event.model_dump(mode="json")


@pytest.mark.asyncio
async def test_submit_uses_inngest_event_bus_by_default(
    session: Session,
    experiment: Experiment,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[object] = []

    async def fake_send(event: object) -> None:
        sent.append(event)

    monkeypatch.setattr(
        "ergon_core.core.application.experiments.submission.inngest_client.send",
        fake_send,
    )
    service = ExperimentSubmissionService(session=session)

    result = await experiment.submit(service=service, k=1, sampler=SequentialSampler())

    assert len(sent) == 1
    assert getattr(sent[0], "name") == WorkflowStartedEvent.name
    assert getattr(sent[0], "data") == {
        "sample_id": str(result.sample_ids[0]),
    }
