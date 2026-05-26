from collections.abc import Iterator
from typing import Literal
from uuid import uuid4

import pytest
from sqlmodel import select

from ergon_core.api import Environment, Experiment, RandomSampler, Sample
from ergon_core.core.persistence.samples.models import SampleTaskEventRow
from ergon_core.test_support.task_factory import task_with_id

pytestmark = pytest.mark.xfail(
    strict=True,
    reason="PR05 implements ExperimentSubmissionService materialization and runtime start",
)


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


@pytest.mark.asyncio
async def test_public_experiment_submit_materializes_samples_and_typed_wal(session) -> None:
    from ergon_core.core.application.experiments.submission import ExperimentSubmissionService

    env = MaterializedEnvironment(name="mini")
    experiment = Experiment(name="mini-smoke", environments=[env])

    result = await experiment.submit(
        service=ExperimentSubmissionService.for_session(session),
        k=1,
        sampler=RandomSampler(seed=0),
    )

    assert result.sample_ids
    assert session.exec(select(SampleTaskEventRow)).all()
