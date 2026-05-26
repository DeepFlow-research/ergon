from collections.abc import Iterator
from typing import Literal
from uuid import uuid4

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

import ergon_core.core.persistence.definitions.models  # noqa: F401
import ergon_core.core.persistence.samples.models  # noqa: F401
import ergon_core.core.persistence.telemetry.models  # noqa: F401
from ergon_core.api import Environment, Experiment, Sample
from ergon_core.core.application.experiments.repositories import (
    persist_experiment,
    record_sampler_invocation,
)
from ergon_core.core.persistence.experiments.models import ExperimentEnvironmentRow
from ergon_core.core.persistence.samples.models import SampleStatusEventRow, SampleTaskEventRow
from ergon_core.core.persistence.telemetry.models import SampleRecord
from ergon_core.test_support.task_factory import task_with_id


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


class MaterializedEnvironment(Environment):
    source_mode: Literal["materialized"] = "materialized"

    def iter_samples(self) -> Iterator[Sample]:
        yield make_sample(self.name, "a")


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture
def two_env_experiment() -> Experiment:
    return Experiment(
        name="persistence smoke",
        description="Persist shape only",
        created_by="unit-test",
        metadata={"suite": "pr04"},
        environments=[
            MaterializedEnvironment(
                name="mini-validation",
                source_metadata={"dataset": "mini"},
                metadata={"split": "validation"},
            ),
            MaterializedEnvironment(
                name="swe-validation",
                source_metadata={"dataset": "swe"},
                metadata={"split": "validation"},
            ),
        ],
    )


def test_persist_experiment_writes_environment_rows(
    session: Session,
    two_env_experiment: Experiment,
) -> None:
    handle = persist_experiment(session=session, experiment=two_env_experiment)

    env_rows = session.exec(
        select(ExperimentEnvironmentRow).where(
            ExperimentEnvironmentRow.experiment_id == handle.experiment_id
        )
    ).all()

    assert handle.experiment_id is not None
    assert [row.name for row in env_rows] == ["mini-validation", "swe-validation"]
    assert session.exec(select(SampleRecord)).all() == []
    assert session.exec(select(SampleStatusEventRow)).all() == []
    assert session.exec(select(SampleTaskEventRow)).all() == []


def test_record_sampler_invocation_writes_no_runtime_state(
    session: Session,
    two_env_experiment: Experiment,
) -> None:
    handle = persist_experiment(session=session, experiment=two_env_experiment)

    invocation = record_sampler_invocation(
        session=session,
        experiment_ref=handle,
        sampler_name="random",
        requested_k=4,
        candidate_pool_size=16,
        selected_count=0,
        sampler_config={"seed": 1},
    )

    assert invocation.experiment_id == handle.experiment_id
    assert session.exec(select(SampleRecord)).all() == []
    assert session.exec(select(SampleTaskEventRow)).all() == []
