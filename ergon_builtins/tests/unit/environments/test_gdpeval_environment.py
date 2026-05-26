from __future__ import annotations

import json

from ergon_builtins.benchmarks.gdpeval.benchmark import GDPEvalTask
from ergon_builtins.benchmarks.gdpeval.task_schemas import GDPTaskConfig
from ergon_core.api import Sample


def test_gdpeval_environment_returns_samples(gdpeval_environment_factory) -> None:
    env = gdpeval_environment_factory(limit=1)

    sample = next(iter(env.iter_samples()))

    assert isinstance(sample, Sample)
    assert sample.sample_key == "gdp-1"
    assert sample.environment_name == env.name
    assert sample.tasks
    assert sample.tasks[0].worker is not None
    assert sample.tasks[0].sandbox is not None
    assert sample.tasks[0].evaluators
    assert isinstance(sample.tasks[0], GDPEvalTask)
    assert isinstance(sample.tasks[0].task_payload, GDPTaskConfig)


def test_gdpeval_materialized_environment_supports_all_samples(gdpeval_environment_factory) -> None:
    env = gdpeval_environment_factory(limit=2)

    samples = env.all_samples()

    assert len(samples) == 2
    assert [sample.sample_key for sample in samples] == ["gdp-1", "gdp-2"]


def test_gdpeval_sample_provenance_is_json_safe(gdpeval_environment_factory) -> None:
    sample = next(iter(gdpeval_environment_factory(limit=1).iter_samples()))

    json.dumps(sample.sample_ref)
    json.dumps(sample.source_metadata)
