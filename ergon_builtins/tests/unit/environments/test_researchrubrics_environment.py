from __future__ import annotations

import json

from ergon_builtins.benchmarks.researchrubrics.benchmark import ResearchRubricsTask
from ergon_builtins.benchmarks.researchrubrics.task_schemas import ResearchRubricsTaskPayload
from ergon_core.api import Sample


def test_researchrubrics_environment_returns_samples(researchrubrics_environment_factory) -> None:
    env = researchrubrics_environment_factory(limit=1)

    sample = next(iter(env.iter_samples()))

    assert isinstance(sample, Sample)
    assert sample.sample_key == "research-1"
    assert sample.environment_name == env.name
    assert sample.tasks
    assert sample.tasks[0].worker is not None
    assert sample.tasks[0].sandbox is not None
    assert sample.tasks[0].evaluators
    assert isinstance(sample.tasks[0], ResearchRubricsTask)
    assert isinstance(sample.tasks[0].task_payload, ResearchRubricsTaskPayload)


def test_researchrubrics_materialized_environment_supports_all_samples(
    researchrubrics_environment_factory,
) -> None:
    env = researchrubrics_environment_factory(limit=2)

    samples = env.all_samples()

    assert len(samples) == 2
    assert [sample.sample_key for sample in samples] == ["research-1", "research-2"]


def test_researchrubrics_sample_provenance_is_json_safe(
    researchrubrics_environment_factory,
) -> None:
    sample = next(iter(researchrubrics_environment_factory(limit=1).iter_samples()))

    json.dumps(sample.sample_ref)
    json.dumps(sample.source_metadata)
