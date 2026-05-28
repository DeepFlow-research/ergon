"""Sample-centered getting-started example tests."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

from ergon_core.api import Environment, Evaluator, ExperimentSubmitResult, Sample, Sandbox, Worker
from ergon_core.api.worker.results import WorkerOutput
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
    def iter_samples(self):
        return iter(())


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
            experiment_id=UUID("11111111-1111-1111-1111-111111111111"),
            sampler_invocation_id=UUID("22222222-2222-2222-2222-222222222222"),
            requested_k=k,
            candidate_pool_size=k,
            selected_count=k,
            sample_ids=[UUID("33333333-3333-3333-3333-333333333333")],
        )


class FakeWorker(Worker):
    type_slug = "fake-worker"

    max_iterations: int | None = None
    system_prompt: str | None = None
    toolkit: object | None = None

    async def execute(self, task, *, context):
        del task, context
        if False:
            yield WorkerOutput(output="ok")


class FakeSandbox(Sandbox):
    async def provision(self) -> None:
        return None

    async def _bind_runtime(self, sandbox_id: str) -> None:
        del sandbox_id
        return None


class FakeEvaluator(Evaluator):
    type_slug = "fake-evaluator"

    def criteria_for(self, task):
        del task
        return []

    def aggregate_task(self, task, criterion_results):
        del task, criterion_results
        raise NotImplementedError


class FakeComponent:
    def __init__(self, *args, **kwargs) -> None:
        self.args = args
        self.kwargs = kwargs


@pytest.mark.asyncio
async def test_getting_started_submit_uses_experiment_api(monkeypatch, capsys) -> None:
    module = _load_submit_module()
    observed: dict[str, object] = {}

    def fake_preflight(*, base_url: str) -> object:
        observed["preflight_base_url"] = base_url
        return object()

    def fake_load_rows(*, split: str, limit: int) -> list[SimpleNamespace]:
        observed["load_rows"] = {"split": split, "limit": limit}
        return [SimpleNamespace(name="sample-1")]

    def fake_make_sample(
        row, *, environment_name: str, worker, evaluators, sandbox, **kwargs
    ) -> Sample:
        observed["sample_kwargs"] = {
            "row": row,
            "environment_name": environment_name,
            "worker": worker,
            "evaluators": evaluators,
            "sandbox": sandbox,
            **kwargs,
        }
        return Sample.from_tasks(
            name=f"{environment_name}:{row.name}",
            sample_key=row.name,
            environment_name=environment_name,
            tasks=[
                task_with_id(
                    UUID("00000000-0000-0000-0000-000000000011"),
                    task_slug="solve",
                    instance_key=row.name,
                    description="Solve sample 1",
                    worker=worker,
                    evaluators=tuple(evaluators),
                    sandbox=sandbox,
                )
            ],
        )

    class CapturingEnvironment:
        @classmethod
        def from_records(cls, **kwargs) -> FakeEnvironment:
            observed["environment_kwargs"] = kwargs
            samples = [kwargs["make_sample"](row) for row in kwargs["records"]]
            observed["samples"] = samples
            return FakeEnvironment(name=kwargs["name"])

    monkeypatch.setattr(module, "preflight_llamacpp_and_e2b", fake_preflight)
    monkeypatch.setattr(module, "Environment", CapturingEnvironment)
    monkeypatch.setattr(module, "ReActWorker", FakeWorker)
    monkeypatch.setattr(module, "MiniF2FToolkit", FakeComponent)
    monkeypatch.setattr(module, "MiniF2FRubric", FakeEvaluator)
    monkeypatch.setattr(module, "LeanSandbox", FakeSandbox)
    monkeypatch.setattr(module, "load_minif2f_rows", fake_load_rows)
    monkeypatch.setattr(module, "make_minif2f_sample", fake_make_sample)
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
    assert observed["load_rows"] == {"split": "validation", "limit": 2}
    assert (
        observed["sample_kwargs"]["worker"].model
        == "llamacpp:http://localhost:8080#local-proof-model"
    )
    assert observed["sample_kwargs"]["worker"].max_iterations == 4
    assert observed["environment_kwargs"]["name"] == "mini-validation"
    output = json.loads(capsys.readouterr().out)
    assert output == {
        "experiment_id": "11111111-1111-1111-1111-111111111111",
        "sampler_invocation_id": "22222222-2222-2222-2222-222222222222",
        "batch_id": None,
        "sample_ids": ["33333333-3333-3333-3333-333333333333"],
    }


def test_getting_started_source_has_no_definition_launch_path() -> None:
    source = _SUBMIT_PATH.read_text()

    assert "MiniF2FBenchmark" not in source
    assert "persist_benchmark" not in source
    assert "launch_run" not in source
    assert "definition_id" not in source
    assert "run_ids" not in source
