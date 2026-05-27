from collections.abc import Iterator
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID, uuid4

import pytest

from ergon_core.api import (
    Environment,
    Experiment,
    ExperimentRef,
    ExperimentSubmitResult,
    persist_experiment,
    RandomSampler,
    Sample,
    SamplingContext,
)
from ergon_core.test_support.task_factory import task_with_id


def make_sample(key: str) -> Sample:
    return Sample.from_tasks(
        name=f"sample:{key}",
        sample_key=key,
        environment_name="mini",
        tasks=[
            task_with_id(
                uuid4(),
                task_slug=f"solve-{key}",
                instance_key=key,
                description=f"Solve {key}",
            )
        ],
    )


class MaterializedEnvironment(Environment):
    source_mode: Literal["materialized"] = "materialized"

    def iter_samples(self) -> Iterator[Sample]:
        yield make_sample("a")


class StreamingEnvironment(Environment):
    source_mode: Literal["streaming"] = "streaming"
    next_index: int = 0

    def iter_samples(self) -> Iterator[Sample]:
        while True:
            key = str(self.next_index)
            self.next_index += 1
            yield make_sample(key)


@pytest.mark.asyncio
async def test_random_sampler_returns_all_candidates_in_seeded_order_without_truncating() -> None:
    samples = [make_sample(str(index)) for index in range(5)]
    selected = await RandomSampler(seed=7).select(
        samples=samples,
        k=2,
        context=SamplingContext(experiment_id=uuid4()),
    )

    assert sorted(sample.sample_key for sample in selected) == ["0", "1", "2", "3", "4"]
    assert [sample.sample_key for sample in selected] != ["0", "1", "2", "3", "4"]


class FakeSubmissionService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def submit(
        self,
        *,
        experiment: Experiment,
        k: int,
        sampler: RandomSampler,
        candidate_pool_size: int | None,
        policy_version: int | None,
    ) -> ExperimentSubmitResult:
        self.calls.append(
            {
                "experiment": experiment,
                "k": k,
                "sampler": sampler,
                "candidate_pool_size": candidate_pool_size,
                "policy_version": policy_version,
            }
        )
        return ExperimentSubmitResult(
            experiment_id=uuid4(),
            requested_k=k,
            candidate_pool_size=candidate_pool_size or k,
            selected_count=0,
            sample_ids=[],
        )


@pytest.mark.asyncio
async def test_experiment_submit_validates_then_delegates_to_service() -> None:
    service = FakeSubmissionService()
    experiment = Experiment(name="x", environments=[MaterializedEnvironment(name="m")])

    result = await experiment.submit(service=service, k=1, sampler=RandomSampler(seed=1))

    assert isinstance(result.experiment_id, UUID)
    assert service.calls[0]["k"] == 1
    assert service.calls[0]["experiment"] is experiment


def test_experiment_rejects_duplicate_environment_names() -> None:
    experiment = Experiment(
        name="x",
        environments=[MaterializedEnvironment(name="m"), MaterializedEnvironment(name="m")],
    )

    with pytest.raises(ValueError, match="unique"):
        experiment.validate_authoring()


def test_streaming_environment_candidate_cursor_does_not_replay() -> None:
    environment = StreamingEnvironment(name="stream")

    first = [sample.sample_key for _, sample in zip(range(3), environment.iter_candidate_samples())]
    second = [
        sample.sample_key for _, sample in zip(range(2), environment.iter_candidate_samples())
    ]

    assert first == ["0", "1", "2"]
    assert second == ["3", "4"]


def test_experiment_can_remember_persisted_ref_between_submissions() -> None:
    experiment = Experiment(name="x", environments=[MaterializedEnvironment(name="m")])
    ref = ExperimentRef(experiment_id=uuid4(), name="x")

    experiment.mark_persisted(ref)

    assert experiment.persisted_ref() == ref


class FakePersistenceService:
    def __init__(self) -> None:
        self.calls: list[Experiment] = []

    async def persist_experiment(self, experiment: Experiment):
        self.calls.append(experiment)
        raise AssertionError("invalid experiment should not reach persistence service")


@pytest.mark.asyncio
async def test_persist_experiment_validates_before_delegating() -> None:
    service = FakePersistenceService()

    with pytest.raises(ValueError, match="Experiment name is required"):
        await persist_experiment(Experiment(name="", environments=[]), service=service)

    assert service.calls == []


def test_public_experiment_api_uses_experiment_id_names() -> None:
    ref = ExperimentRef(
        experiment_id=uuid4(),
        name="demo",
        environment_ids={},
        created_at=datetime.now(timezone.utc),
        metadata={},
    )
    result = ExperimentSubmitResult(
        experiment_id=ref.experiment_id,
        requested_k=1,
        candidate_pool_size=1,
        selected_count=0,
        sample_ids=[],
    )
    context = SamplingContext(experiment_id=ref.experiment_id)

    assert ref.experiment_id
    assert result.experiment_id == ref.experiment_id
    assert context.experiment_id == ref.experiment_id


def test_public_persistence_facade_is_owned_by_api_package() -> None:
    from ergon_core.api.experiment.persistence import persist_experiment as facade

    assert facade is persist_experiment
