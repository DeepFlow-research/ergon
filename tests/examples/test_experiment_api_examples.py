"""Smoke tests for public experiment API examples."""

from __future__ import annotations

import asyncio
import importlib.util
import json
from collections.abc import Iterator, Sequence
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

from pydantic import ConfigDict

from ergon_core.api import (
    Environment,
    Evaluator,
    Experiment,
    ExperimentSubmitResult,
    Sample,
    Sandbox,
    Worker,
)
from ergon_core.api.worker.results import WorkerOutput
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
            experiment_id=UUID("00000000-0000-0000-0000-000000000001"),
            sampler_invocation_id=UUID("00000000-0000-0000-0000-000000000002"),
            requested_k=k,
            candidate_pool_size=candidate_pool_size or k,
            selected_count=min(k, len(selected)),
            sample_ids=[UUID("00000000-0000-0000-0000-000000000003")],
        )


class FakeComponent:
    def __init__(self, *args, **kwargs) -> None:
        self.args = args
        self.kwargs = kwargs


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


class FakeEnvironmentFactory:
    calls: list[dict[str, object]] = []

    @classmethod
    def from_records(cls, **kwargs) -> FakeEnvironment:
        cls.calls.append({"constructor": "from_records", **kwargs})
        return FakeEnvironment(
            name=kwargs["name"], source_mode=kwargs.get("source_mode", "materialized")
        )

    @classmethod
    def from_dataset(cls, **kwargs) -> FakeEnvironment:
        cls.calls.append({"constructor": "from_dataset", **kwargs})
        return FakeEnvironment(
            name=kwargs["name"], source_mode=kwargs.get("source_mode", "streaming")
        )


def _fake_rows(*, limit: int | None = None, **kwargs) -> list[SimpleNamespace]:
    del kwargs
    size = limit or 1
    return [
        SimpleNamespace(
            name=f"row-{index}",
            repo="django/django" if index == 0 else "python/cpython",
            difficulty=index,
        )
        for index in range(size)
    ]


def _fake_streaming_rows(*, limit: int | None = None, **kwargs) -> Iterator[SimpleNamespace]:
    yield from _fake_rows(limit=limit or 1, **kwargs)


def _fake_sample_from_row(row, *, environment_name: str, **kwargs) -> Sample:
    key = getattr(row, "name", getattr(row, "instance_id", "sample-1"))
    task_kwargs = {}
    for name in ("worker", "sandbox", "evaluators"):
        if name in kwargs:
            task_kwargs[name] = kwargs[name]
    return Sample.from_tasks(
        name=f"{environment_name}:{key}",
        sample_key=str(key),
        environment_name=environment_name,
        tasks=[
            task_with_id(
                uuid4(),
                task_slug="solve",
                instance_key=str(key),
                description=f"Solve {key}",
                **task_kwargs,
            )
        ],
    )


def _patch_existing(monkeypatch, module, names: Sequence[str], replacement) -> None:
    for name in names:
        if hasattr(module, name):
            monkeypatch.setattr(module, name, replacement)


def _stub_runtime_components(monkeypatch, module) -> None:
    FakeEnvironmentFactory.calls = []
    monkeypatch.setattr(module, "Environment", FakeEnvironmentFactory)
    _patch_existing(
        monkeypatch,
        module,
        (
            "MiniF2FToolkit",
            "ResearchRubricsToolkit",
            "GDPEvalToolkit",
            "SWEBenchToolkit",
        ),
        FakeComponent,
    )
    _patch_existing(monkeypatch, module, ("ReActWorker",), FakeWorker)
    _patch_existing(
        monkeypatch,
        module,
        ("LeanSandbox", "ResearchE2BSandbox", "GDPEvalSandbox", "SWEBenchSandbox"),
        FakeSandbox,
    )
    _patch_existing(
        monkeypatch,
        module,
        ("MiniF2FRubric", "ResearchRubricsRubric", "StagedRubric", "SWEBenchRubric"),
        FakeEvaluator,
    )
    _patch_existing(
        monkeypatch,
        module,
        ("load_minif2f_rows", "load_researchrubrics_rows", "load_gdpeval_rows"),
        _fake_rows,
    )
    _patch_existing(monkeypatch, module, ("iter_swebench_rows",), _fake_streaming_rows)
    _patch_existing(
        monkeypatch,
        module,
        (
            "make_minif2f_sample",
            "make_researchrubrics_sample",
            "make_gdpeval_sample",
            "make_swebench_sample",
        ),
        _fake_sample_from_row,
    )


def test_minif2f_example_prints_sample_ids_not_run_ids(monkeypatch, capsys) -> None:
    module = _load_submit_module("01_minif2f_single_environment")
    service = FakeSubmissionService()
    _stub_runtime_components(monkeypatch, module)
    monkeypatch.setattr(module, "experiment_submission_service", lambda: service)

    asyncio.run(module.main())

    output = json.loads(capsys.readouterr().out)
    assert output["experiment_id"]
    assert output["sampler_invocation_id"]
    assert output["sample_ids"]
    assert "experiment_ref_id" not in output
    assert "run_ids" not in output
    assert "definition_id" not in output


def test_mixed_environment_example_composes_all_builtin_environments(monkeypatch) -> None:
    module = _load_submit_module("02_mixed_environment_training")
    service = FakeSubmissionService()
    _stub_runtime_components(monkeypatch, module)
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
    monkeypatch.setattr(module, "experiment_submission_service", lambda: service)

    asyncio.run(module.main())

    call = service.submit_calls[0]
    assert call["k"] == 8
    assert call["candidate_pool_size"] == 32


def test_curriculum_example_uses_custom_sampler_and_larger_pool(monkeypatch) -> None:
    module = _load_submit_module("04_curriculum_sampler")
    service = FakeSubmissionService()
    _stub_runtime_components(monkeypatch, module)
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
        @classmethod
        def from_dataset(cls, **kwargs) -> FakeEnvironment:
            row = next(iter(kwargs["dataset"]))
            sample = kwargs["make_sample"](row)
            captured["sample"] = sample
            captured["worker"] = sample.tasks[0].worker
            captured["evaluators"] = sample.tasks[0].evaluators
            captured["sandbox"] = sample.tasks[0].sandbox
            return FakeEnvironment(
                name=kwargs["name"], source_mode=kwargs.get("source_mode", "streaming")
            )

    _stub_runtime_components(monkeypatch, module)
    monkeypatch.setattr(module, "Environment", CapturingEnvironment)
    monkeypatch.setattr(module, "experiment_submission_service", lambda: FakeSubmissionService())

    asyncio.run(module.main())

    assert isinstance(captured["worker"], FakeWorker)
    assert captured["worker"].model == "openai:gpt-4o"
    assert captured["evaluators"]
    assert isinstance(captured["sandbox"], FakeSandbox)
