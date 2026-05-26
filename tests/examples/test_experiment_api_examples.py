"""Smoke tests for public experiment API examples."""

from __future__ import annotations

import asyncio
import importlib.util
import json
from collections.abc import Iterator, Sequence
from pathlib import Path
from uuid import UUID, uuid4

from pydantic import ConfigDict

from ergon_core.api import Environment, Experiment, ExperimentSubmitResult, Sample
from ergon_core.api.experiment.sampling import SamplingContext
from ergon_core.test_support.task_factory import task_with_id

_EXAMPLES_ROOT = Path(__file__).parents[2] / "examples" / "experiment_api"


def _load_submit_module(example_dir: str):
    path = _EXAMPLES_ROOT / example_dir / "submit.py"
    spec = importlib.util.spec_from_file_location(f"example_{example_dir}", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sample(key: str = "sample-1", environment_name: str = "fake") -> Sample:
    return Sample.from_tasks(
        name=f"{environment_name}:{key}",
        sample_key=key,
        environment_name=environment_name,
        tasks=[
            task_with_id(
                uuid4(),
                task_slug="solve",
                instance_key=key,
                description=f"Solve {key}",
            )
        ],
    )


class FakeEnvironment(Environment):
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    def iter_samples(self) -> Iterator[Sample]:
        yield _sample(environment_name=self.name)


class FakeSubmissionService:
    def __init__(self) -> None:
        self.submitted_experiments: list[Experiment] = []
        self.submit_calls: list[dict[str, object]] = []

    async def submit(
        self,
        *,
        experiment: Experiment,
        k: int,
        sampler,
        candidate_pool_size: int | None,
        policy_version: int | None,
    ) -> ExperimentSubmitResult:
        del policy_version
        samples = [_sample(str(index), "fake") for index in range(candidate_pool_size or k)]
        selected = await sampler.select(
            samples=samples,
            k=k,
            context=SamplingContext(experiment_ref_id=uuid4(), candidate_pool_size=len(samples)),
        )
        self.submitted_experiments.append(experiment)
        self.submit_calls.append(
            {
                "k": k,
                "candidate_pool_size": candidate_pool_size,
                "sampler": sampler,
                "candidate_count_seen_by_sampler": len(selected),
            }
        )
        return ExperimentSubmitResult(
            experiment_ref_id=UUID("00000000-0000-0000-0000-000000000001"),
            sampler_invocation_id=UUID("00000000-0000-0000-0000-000000000002"),
            requested_k=k,
            candidate_pool_size=candidate_pool_size or k,
            selected_count=min(k, len(selected)),
            sample_ids=[UUID("00000000-0000-0000-0000-000000000003")],
        )


def _stub_runtime_components(monkeypatch, module) -> None:
    for name in (
        "make_minif2f_worker",
        "make_minif2f_rubric",
        "make_gdpeval_worker",
        "make_gdpeval_rubric",
        "make_research_rubric",
        "make_swebench_worker",
        "make_swebench_rubric",
    ):
        if hasattr(module, name):
            monkeypatch.setattr(module, name, lambda *args, **kwargs: object())
    for name in (
        "LeanSandbox",
        "_default_gdpeval_sandbox",
        "_default_research_sandbox",
        "_default_swebench_sandbox",
        "SWEBenchSandbox",
    ):
        if hasattr(module, name):
            monkeypatch.setattr(module, name, lambda *args, **kwargs: object())


def test_minif2f_example_prints_sample_ids_not_run_ids(monkeypatch, capsys) -> None:
    module = _load_submit_module("01_minif2f_single_environment")
    service = FakeSubmissionService()
    _stub_runtime_components(monkeypatch, module)
    monkeypatch.setattr(module, "experiment_submission_service", lambda: service)
    monkeypatch.setattr(module, "MiniF2FEnvironment", FakeEnvironment)

    asyncio.run(module.main())

    output = json.loads(capsys.readouterr().out)
    assert output["experiment_ref_id"]
    assert output["sampler_invocation_id"]
    assert output["sample_ids"]
    assert "run_ids" not in output
    assert "definition_id" not in output


def test_mixed_environment_example_composes_all_builtin_environments(monkeypatch) -> None:
    module = _load_submit_module("02_mixed_environment_training")
    service = FakeSubmissionService()
    _stub_runtime_components(monkeypatch, module)
    for name in (
        "MiniF2FEnvironment",
        "ResearchRubricsEnvironment",
        "GDPEvalEnvironment",
        "SweBenchVerifiedEnvironment",
    ):
        monkeypatch.setattr(module, name, FakeEnvironment)
    monkeypatch.setattr(module, "experiment_submission_service", lambda: service)

    asyncio.run(module.main())

    experiment = service.submitted_experiments[0]
    assert [env.name for env in experiment.environments] == [
        "mini-validation",
        "research-validation",
        "gdp-validation",
        "swebench-train",
    ]


def test_streaming_example_uses_candidate_pool_larger_than_k(monkeypatch) -> None:
    module = _load_submit_module("03_streaming_hf_dataset")
    service = FakeSubmissionService()
    _stub_runtime_components(monkeypatch, module)
    monkeypatch.setattr(module, "SweBenchVerifiedEnvironment", FakeEnvironment)
    monkeypatch.setattr(module, "experiment_submission_service", lambda: service)

    asyncio.run(module.main())

    call = service.submit_calls[0]
    assert call["k"] == 8
    assert call["candidate_pool_size"] == 32


def test_curriculum_example_uses_custom_sampler_and_larger_pool(monkeypatch) -> None:
    module = _load_submit_module("04_curriculum_sampler")
    service = FakeSubmissionService()
    monkeypatch.setattr(module, "MiniF2FEnvironment", FakeEnvironment)
    monkeypatch.setattr(module, "experiment_submission_service", lambda: service)

    asyncio.run(module.main())

    call = service.submit_calls[0]
    assert call["k"] == 16
    assert call["candidate_pool_size"] == 64
    assert call["sampler"].name == "easy-first"
    assert call["candidate_count_seen_by_sampler"] == 64


def test_row_dependent_example_passes_runtime_config_callables(monkeypatch) -> None:
    module = _load_submit_module("05_row_dependent_runtime_configs")
    captured: dict[str, object] = {}

    class CapturingEnvironment(FakeEnvironment):
        def __init__(self, **kwargs) -> None:
            captured.update(kwargs)
            super().__init__(**kwargs)

    _stub_runtime_components(monkeypatch, module)
    monkeypatch.setattr(module, "SweBenchVerifiedEnvironment", CapturingEnvironment)
    monkeypatch.setattr(module, "experiment_submission_service", lambda: FakeSubmissionService())

    asyncio.run(module.main())

    assert callable(captured["worker"])
    assert callable(captured["evaluators"])
    assert callable(captured["sandbox"])
