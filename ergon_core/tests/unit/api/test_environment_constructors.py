from collections.abc import Iterable
from itertools import islice
from uuid import uuid4

import pytest

from ergon_core.api import Environment, Sample
from ergon_core.test_support.task_factory import task_with_id


def make_sample(row: str) -> Sample:
    return Sample.from_tasks(
        name=f"sample:{row}",
        sample_key=row,
        environment_name="records",
        tasks=[
            task_with_id(
                uuid4(),
                task_slug=f"solve-{row}",
                instance_key=row,
                description=f"Solve {row}",
            )
        ],
    )


def test_from_records_materializes_rows_to_samples() -> None:
    env = Environment.from_records(
        name="records",
        records=["a", "b"],
        make_sample=make_sample,
    )

    assert env.source_mode == "materialized"
    assert [sample.sample_key for sample in env.all_samples()] == ["a", "b"]
    assert [sample.sample_key for sample in env.all_samples()] == ["a", "b"]


def test_from_dataset_streams_rows_to_samples_without_replaying_cursor() -> None:
    def rows() -> Iterable[str]:
        yield "a"
        yield "b"
        yield "c"

    env = Environment.from_dataset(
        name="dataset",
        dataset=rows(),
        make_sample=make_sample,
    )

    assert env.source_mode == "streaming"
    with pytest.raises(NotImplementedError):
        env.all_samples()

    first = [sample.sample_key for sample in islice(env.iter_candidate_samples(), 2)]
    second = [sample.sample_key for sample in islice(env.iter_candidate_samples(), 1)]

    assert first == ["a", "b"]
    assert second == ["c"]
