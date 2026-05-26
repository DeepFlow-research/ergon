from collections.abc import Iterator
from itertools import islice
from typing import Literal
from uuid import uuid4

import pytest

from ergon_core.api import Environment, Sample
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


class StreamOnlyEnvironment(Environment):
    source_mode: Literal["streaming"] = "streaming"

    def iter_samples(self) -> Iterator[Sample]:
        yield make_sample("a")
        yield make_sample("b")


def test_environment_can_be_stream_only() -> None:
    env = StreamOnlyEnvironment(name="streamed")

    assert [sample.sample_key for sample in islice(env.iter_samples(), 2)] == ["a", "b"]
    with pytest.raises(NotImplementedError):
        env.all_samples()


class MaterializedEnvironment(Environment):
    source_mode: Literal["materialized"] = "materialized"

    def iter_samples(self) -> Iterator[Sample]:
        yield make_sample("a")


def test_materialized_environment_all_samples_uses_iterator() -> None:
    assert [sample.sample_key for sample in MaterializedEnvironment(name="m").all_samples()] == [
        "a"
    ]


def test_environment_rejects_empty_name() -> None:
    with pytest.raises(ValueError, match="name"):
        StreamOnlyEnvironment(name="").validate_authoring()
