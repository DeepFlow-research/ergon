"""Sample-centered getting-started example tests."""

from __future__ import annotations

import importlib.util
import json
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ConfigDict

from ergon_core.api import Environment, ExperimentSubmitResult, Sample
from ergon_core.test_support.task_factory import task_with_id

_SUBMIT_PATH = (
    Path(__file__).parents[2]
    / "examples"
    / "getting_started"
    / "01_minif2f_local_llamacpp"
    / "submit.py"
)


def _load_submit_module():
    spec = importlib.util.spec_from_file_location("minif2f_local_llamacpp_submit", _SUBMIT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeEnvironment(Environment):
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    def iter_samples(self) -> Iterator[Sample]:
        yield Sample.from_tasks(
            name="mini-validation:sample-1",
            sample_key="sample-1",
            environment_name=self.name,
            tasks=[
                task_with_id(
                    UUID("00000000-0000-0000-0000-000000000011"),
                    description="Solve sample 1",
                )
            ],
        )


class FakeSubmissionService:
    async def submit(
        self,
        *,
        experiment,
        k: int,
        sampler,
        candidate_pool_size: int | None,
        policy_version: int | None,
    ) -> ExperimentSubmitResult:
        del experiment, sampler, candidate_pool_size, policy_version
        return ExperimentSubmitResult(
            experiment_ref_id=UUID("11111111-1111-1111-1111-111111111111"),
            sampler_invocation_id=UUID("22222222-2222-2222-2222-222222222222"),
            requested_k=k,
            candidate_pool_size=k,
            selected_count=k,
            sample_ids=[UUID("33333333-3333-3333-3333-333333333333")],
        )


@pytest.mark.asyncio
async def test_getting_started_submit_uses_experiment_api(monkeypatch, capsys) -> None:
    module = _load_submit_module()
    observed: dict[str, object] = {}

    def fake_preflight(*, base_url: str) -> object:
        observed["preflight_base_url"] = base_url
        return object()

    def fake_make_worker(*, model: str, max_iterations: int) -> object:
        observed["worker_model"] = model
        observed["worker_max_iterations"] = max_iterations
        return object()

    class CapturingEnvironment(FakeEnvironment):
        def __init__(self, **kwargs) -> None:
            observed["environment_kwargs"] = kwargs
            super().__init__(**kwargs)

    monkeypatch.setattr(module, "preflight_llamacpp_and_e2b", fake_preflight)
    monkeypatch.setattr(module, "MiniF2FEnvironment", CapturingEnvironment)
    monkeypatch.setattr(module, "make_minif2f_worker", fake_make_worker)
    monkeypatch.setattr(module, "make_minif2f_rubric", lambda: object())
    monkeypatch.setattr(module, "LeanSandbox", lambda: object())
    monkeypatch.setattr(module, "experiment_submission_service", lambda: FakeSubmissionService())

    exit_code = await module.async_main(
        [
            "--limit",
            "2",
            "--base-url",
            "http://localhost:8080",
            "--model",
            "local-proof-model",
            "--max-iterations",
            "4",
            "--json",
        ]
    )

    assert exit_code == 0
    assert observed["preflight_base_url"] == "http://localhost:8080"
    assert observed["worker_model"] == "llamacpp:http://localhost:8080#local-proof-model"
    assert observed["worker_max_iterations"] == 4
    assert observed["environment_kwargs"]["limit"] == 2
    output = json.loads(capsys.readouterr().out)
    assert output == {
        "experiment_id": "11111111-1111-1111-1111-111111111111",
        "sample_ids": ["33333333-3333-3333-3333-333333333333"],
    }


def test_getting_started_source_has_no_definition_launch_path() -> None:
    source = _SUBMIT_PATH.read_text()

    assert "MiniF2FBenchmark" not in source
    assert "persist_benchmark" not in source
    assert "launch_run" not in source
    assert "definition_id" not in source
    assert "run_ids" not in source
