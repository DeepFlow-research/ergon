"""Contracts for object-bound built-in benchmark classes."""

import pytest
from ergon_builtins.benchmarks.minif2f.benchmark import MiniF2FBenchmark
from ergon_builtins.benchmarks.researchrubrics.benchmark import ResearchRubricsBenchmark
from ergon_builtins.benchmarks.swebench_verified.benchmark import SweBenchVerifiedBenchmark
from ergon_core.api.benchmark import Benchmark, BenchmarkRequirements, EmptyTaskPayload, Task
from pydantic import BaseModel, ValidationError
from ergon_core.test_support.task_factory import TestSandbox, TestWorker

CORE_BENCHMARKS = {
    MiniF2FBenchmark.type_slug: MiniF2FBenchmark,
    SweBenchVerifiedBenchmark.type_slug: SweBenchVerifiedBenchmark,
}

DATA_BENCHMARKS = {
    ResearchRubricsBenchmark.type_slug: ResearchRubricsBenchmark,
}


def _require_onboarding_deps(slug: str, cls: type[Benchmark]) -> BenchmarkRequirements:
    deps = cls.onboarding_deps
    assert isinstance(deps, BenchmarkRequirements), (
        f"Benchmark '{slug}' ({cls.__qualname__}).onboarding_deps is not a "
        f"BenchmarkRequirements instance; got {type(deps)!r}."
    )
    return deps


class TestBenchmarkOnboardingDepsContract:
    """Every importable benchmark must declare onboarding_deps."""

    @pytest.mark.parametrize("slug, cls", [*CORE_BENCHMARKS.items(), *DATA_BENCHMARKS.items()])
    def test_benchmarks_have_onboarding_deps(self, slug: str, cls: type[Benchmark]) -> None:
        _require_onboarding_deps(slug, cls)

    @pytest.mark.parametrize("slug, cls", [*CORE_BENCHMARKS.items(), *DATA_BENCHMARKS.items()])
    def test_benchmarks_declare_payload_models(self, slug: str, cls: type[Benchmark]) -> None:
        assert issubclass(cls.task_payload_model, BaseModel), (
            f"Benchmark '{slug}' ({cls.__qualname__}) must declare a Pydantic task_payload_model."
        )

    def test_onboarding_deps_is_frozen(self) -> None:
        for cls in CORE_BENCHMARKS.values():
            deps = cls.onboarding_deps
            with pytest.raises(ValidationError):
                setattr(deps, "e2b", not deps.e2b)

    def test_known_e2b_benchmarks(self) -> None:
        assert MiniF2FBenchmark.onboarding_deps.e2b is True
        assert SweBenchVerifiedBenchmark.onboarding_deps.e2b is True


class TestBenchmarkSubclassEnforcement:
    def test_base_class_does_not_validate_subclasses_at_import_time(self) -> None:
        class LocalBenchmark(Benchmark):
            type_slug = "local-test"

            def build_instances(self) -> dict[str, list[Task[EmptyTaskPayload]]]:
                return {}

        assert LocalBenchmark.type_slug == "local-test"
        assert LocalBenchmark.task_payload_model is EmptyTaskPayload


class TestTaskPayloadContract:
    def test_task_payload_is_a_pydantic_model(self) -> None:
        payload = EmptyTaskPayload()
        task = Task(
            task_slug="task",
            instance_key="default",
            description="desc",
            task_payload=payload,
            worker=TestWorker(name="worker", model="test:none"),
            sandbox=TestSandbox(),
        )

        assert task.task_payload is payload

    def test_plain_dict_payload_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Task(
                task_slug="task",
                instance_key="default",
                description="desc",
                task_payload={"loose": "dict"},
                worker=TestWorker(name="worker", model="test:none"),
                sandbox=TestSandbox(),
            )
