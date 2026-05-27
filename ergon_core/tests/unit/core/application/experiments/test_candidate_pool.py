from collections.abc import Iterator
from importlib import import_module
from pathlib import Path
from typing import Literal
from uuid import uuid4

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from ergon_core.api import Environment, Experiment, Sample
from ergon_core.core.application.experiments.candidate_pool import (
    SampleCandidatePool,
    sample_from_pool_entry,
)
from ergon_core.core.application.experiments.repository import (
    persist_experiment,
    record_sampler_invocation,
)
from ergon_core.core.persistence.experiments.models import ExperimentSamplePoolEntryRow
from ergon_core.test_support.task_factory import task_with_id

for module_name in (
    "ergon_core.core.persistence.definitions.models",
    "ergon_core.core.persistence.samples.models",
    "ergon_core.core.persistence.telemetry.models",
):
    import_module(module_name)


def make_sample(environment_name: str, key: str) -> Sample:
    return Sample.from_tasks(
        name=f"{environment_name}:{key}",
        sample_key=key,
        environment_name=environment_name,
        tasks=[
            task_with_id(
                uuid4(),
                task_slug=f"solve-{environment_name}-{key}",
                instance_key=key,
                description=f"Solve {key}",
            )
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


class CountedStreamingEnvironment(StreamingEnvironment):
    pull_count: int = 0

    def iter_samples(self) -> Iterator[Sample]:
        while self.pull_count < self.total:
            index = self.pull_count
            self.pull_count += 1
            yield make_sample(self.name, str(index))


class DuplicateStreamingEnvironment(Environment):
    source_mode: Literal["streaming"] = "streaming"
    pull_count: int = 0

    def iter_samples(self) -> Iterator[Sample]:
        while True:
            self.pull_count += 1
            yield make_sample(self.name, "duplicate")


class MaterializedEnvironment(Environment):
    source_mode: Literal["materialized"] = "materialized"
    keys: tuple[str, ...]

    def iter_samples(self) -> Iterator[Sample]:
        for key in self.keys:
            yield make_sample(self.name, key)


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture
def streamed_experiment() -> Experiment:
    return Experiment(
        name="streamed",
        environments=[StreamingEnvironment(name="stream", total=20)],
    )


@pytest.fixture
def counted_streaming_experiment() -> Experiment:
    return Experiment(
        name="counted",
        environments=[CountedStreamingEnvironment(name="stream", total=20)],
    )


def test_candidate_pool_retains_unselected_streamed_candidates(
    session: Session,
    streamed_experiment: Experiment,
) -> None:
    handle = persist_experiment(session=session, experiment=streamed_experiment)
    pool = SampleCandidatePool(session)

    candidates = pool.fill(
        experiment=streamed_experiment,
        handle=handle,
        candidate_pool_size=8,
    )
    selected = candidates[:3]
    invocation = record_sampler_invocation(
        session=session,
        experiment_ref=handle,
        sampler_name="sequential",
        requested_k=3,
        candidate_pool_size=8,
        selected_count=3,
        sampler_config={},
    )
    pool.mark_selected(selected, sampler_invocation_id=invocation.id)

    rows = session.exec(select(ExperimentSamplePoolEntryRow)).all()
    assert len(rows) == 8
    assert sum(row.selected for row in rows) == 3
    assert sum(row.discarded for row in rows) == 0
    assert rows[0].sample_ref_json == {"key": "0"}
    assert rows[0].sample_json["sample_ref"] == rows[0].sample_ref_json


def test_candidate_pool_reuses_unselected_entries_before_advancing_stream(
    session: Session,
    counted_streaming_experiment: Experiment,
) -> None:
    handle = persist_experiment(session=session, experiment=counted_streaming_experiment)
    pool = SampleCandidatePool(session)

    first = pool.fill(
        experiment=counted_streaming_experiment,
        handle=handle,
        candidate_pool_size=8,
    )
    pool.mark_selected(first[:2], sampler_invocation_id=uuid4())
    session.commit()

    second = pool.fill(
        experiment=counted_streaming_experiment,
        handle=handle,
        candidate_pool_size=8,
    )

    assert [entry.sample_key for entry in second[:6]] == [entry.sample_key for entry in first[2:]]
    assert counted_streaming_experiment.environments[0].pull_count == 10


def test_candidate_pool_round_robins_new_entries_across_environments(
    session: Session,
) -> None:
    experiment = Experiment(
        name="balanced",
        environments=[
            MaterializedEnvironment(name="mini-validation", keys=("a", "b", "c")),
            MaterializedEnvironment(name="swe-validation", keys=("1", "2", "3")),
        ],
    )
    handle = persist_experiment(session=session, experiment=experiment)
    pool = SampleCandidatePool(session)

    entries = pool.fill(experiment=experiment, handle=handle, candidate_pool_size=4)

    assert [entry.sample_json["environment_name"] for entry in entries] == [
        "mini-validation",
        "swe-validation",
        "mini-validation",
        "swe-validation",
    ]
    assert entries[0].sample_json["sample_key"] == "a"
    assert entries[0].sample_ref_json == {"key": "a"}
    assert entries[0].sample_json["tasks"][0]["task_slug"] == "solve-mini-validation-a"


def test_candidate_pool_stops_after_duplicate_pull_budget(
    session: Session,
) -> None:
    duplicate_env = DuplicateStreamingEnvironment(name="stream")
    experiment = Experiment(name="duplicates", environments=[duplicate_env])
    handle = persist_experiment(session=session, experiment=experiment)
    pool = SampleCandidatePool(session, max_duplicate_pulls_per_environment=3)

    entries = pool.fill(experiment=experiment, handle=handle, candidate_pool_size=2)

    assert [entry.sample_key for entry in entries] == ["duplicate"]
    assert duplicate_env.pull_count == 4


def test_candidate_pool_keeps_sql_access_in_repository() -> None:
    source = Path(
        "ergon_core/ergon_core/core/application/experiments/candidate_pool.py"
    ).read_text()

    assert "session.exec" not in source
    assert "select(" not in source


@pytest.mark.asyncio
async def test_candidate_pool_entry_rehydrates_object_bound_sample_without_runtime_task_id(
    session: Session,
) -> None:
    experiment = Experiment(
        name="rehydrate",
        environments=[MaterializedEnvironment(name="mini-validation", keys=("a",))],
    )
    handle = persist_experiment(session=session, experiment=experiment)
    entry = SampleCandidatePool(session).fill(
        experiment=experiment,
        handle=handle,
        candidate_pool_size=1,
    )[0]

    sample = await sample_from_pool_entry(entry)

    assert sample.sample_key == "a"
    assert sample.environment_name == "mini-validation"
    assert sample.tasks[0].task_slug == "solve-mini-validation-a"
    with pytest.raises(RuntimeError, match="not been materialized"):
        _ = sample.tasks[0].task_id
