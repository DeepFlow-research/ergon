"""Tests for the experiments lifecycle façade.

``define_benchmark_experiment`` was deleted in PR 6.5 Phase 2 — tests that
exercised it have been removed.  ``ExperimentService`` was collapsed to
module-level ``persist_benchmark`` (``definition_writer``) and
``run_experiment`` (``service``); coverage lives in
``test_walkthrough_smoketest.py`` and ``test_experiment_launch_service.py``.
"""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from ergon_core.core.application.experiments import definition_writer
from ergon_core.core.application.experiments import service
from ergon_core.core.application.experiments.models import (
    DefinitionHandle,
    ExperimentRunRequest,
    ExperimentRunResult,
)


def test_persist_benchmark_uses_experiments_service_public_facade(monkeypatch) -> None:
    benchmark = SimpleNamespace(type_slug="ci-benchmark")
    handle = DefinitionHandle(definition_id=uuid4(), benchmark_type="ci-benchmark")
    seen: list[object] = []

    def fake_persist(candidate: object) -> DefinitionHandle:
        seen.append(candidate)
        return handle

    monkeypatch.setattr(definition_writer, "persist_benchmark", fake_persist)

    assert service.persist_benchmark(benchmark) == handle
    assert seen == [benchmark]


@pytest.mark.asyncio
async def test_sample_experiment_uses_experiments_service_public_facade(monkeypatch) -> None:
    definition_id = uuid4()
    sample_id = uuid4()
    result = ExperimentRunResult(
        definition_id=definition_id,
        sample_ids=[sample_id],
        definition_ids=[definition_id],
    )
    seen: list[tuple[object, object]] = []

    async def fake_launch_sample(candidate_definition_id, *, emit_workflow_started=None):
        seen.append((candidate_definition_id, emit_workflow_started))
        return result

    monkeypatch.setattr(service, "launch_sample", fake_launch_sample)

    assert await service.run_experiment(ExperimentRunRequest(definition_id=definition_id)) == result
    assert seen == [(definition_id, None)]
