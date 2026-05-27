from collections.abc import Iterator
from importlib import import_module
from typing import Literal
from uuid import uuid4

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from ergon_core.api import Environment, Experiment, RandomSampler, Sample
from ergon_core.core.persistence.samples.models import SampleTaskEventRow
from ergon_core.test_support.task_factory import task_with_id

for module_name in (
    "ergon_core.core.persistence.experiments.models",
    "ergon_core.core.persistence.graph.models",
    "ergon_core.core.persistence.samples.models",
    "ergon_core.core.persistence.telemetry.models",
):
    import_module(module_name)


class MaterializedEnvironment(Environment):
    source_mode: Literal["materialized"] = "materialized"

    def iter_samples(self) -> Iterator[Sample]:
        yield Sample.from_tasks(
            name="mini:a",
            sample_key="a",
            environment_name=self.name,
            tasks=[
                task_with_id(
                    uuid4(),
                    task_slug="solve",
                    instance_key="a",
                    description="Solve a",
                )
            ],
        )


class FakeEventBus:
    async def publish(self, event) -> None:
        pass


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.mark.asyncio
async def test_public_experiment_submit_materializes_samples_and_typed_wal(session) -> None:
    from ergon_core.core.application.experiments.submission import ExperimentSubmissionService

    env = MaterializedEnvironment(name="mini")
    experiment = Experiment(name="mini-smoke", environments=[env])

    result = await experiment.submit(
        service=ExperimentSubmissionService.for_session(session, event_bus=FakeEventBus()),
        k=1,
        sampler=RandomSampler(seed=0),
    )

    assert result.sample_ids
    assert session.exec(select(SampleTaskEventRow)).all()
