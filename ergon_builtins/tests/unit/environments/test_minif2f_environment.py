from __future__ import annotations

import json

from ergon_builtins.benchmarks.minif2f.benchmark import MiniF2FTask
from ergon_builtins.benchmarks.minif2f.task_schemas import MiniF2FTaskPayload
from ergon_core.api import Sample


def test_minif2f_environment_returns_samples(minif2f_environment_factory) -> None:
    env = minif2f_environment_factory(limit=1)

    sample = next(iter(env.iter_samples()))

    assert isinstance(sample, Sample)
    assert sample.sample_key == "mini-1"
    assert sample.environment_name == env.name
    assert sample.tasks
    assert sample.tasks[0].worker is not None
    assert sample.tasks[0].sandbox is not None
    assert sample.tasks[0].evaluators
    assert isinstance(sample.tasks[0], MiniF2FTask)
    assert isinstance(sample.tasks[0].task_payload, MiniF2FTaskPayload)


def test_minif2f_materialized_environment_supports_all_samples(minif2f_environment_factory) -> None:
    env = minif2f_environment_factory(limit=2)

    samples = env.all_samples()

    assert len(samples) == 2
    assert [sample.sample_key for sample in samples] == ["mini-1", "mini-2"]


def test_minif2f_sample_provenance_is_json_safe(minif2f_environment_factory) -> None:
    sample = next(iter(minif2f_environment_factory(limit=1).iter_samples()))

    json.dumps(sample.sample_ref)
    json.dumps(sample.source_metadata)
