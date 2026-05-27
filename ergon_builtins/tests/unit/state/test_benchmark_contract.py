"""Contracts for object-bound built-in benchmark classes."""

import pytest
from ergon_builtins.benchmarks.minif2f.benchmark import MiniF2FBenchmark
from ergon_builtins.benchmarks.researchrubrics.benchmark import ResearchRubricsBenchmark
from ergon_builtins.benchmarks.swebench_verified.benchmark import SweBenchVerifiedBenchmark
from ergon_core.api.benchmark import Benchmark, EmptyTaskPayload, Task
from pydantic import BaseModel, ValidationError
from ergon_core.test_support.task_factory import TestSandbox, TestWorker

CORE_BENCHMARKS = {
    MiniF2FBenchmark.type_slug: MiniF2FBenchmark,
    SweBenchVerifiedBenchmark.type_slug: SweBenchVerifiedBenchmark,
}

DATA_BENCHMARKS = {
    ResearchRubricsBenchmark.type_slug: ResearchRubricsBenchmark,
}


class TestBenchmarkDependencyMetadataContract:
    """Every importable benchmark exposes current runtime dependency metadata."""

    @pytest.mark.parametrize("slug, cls", [*CORE_BENCHMARKS.items(), *DATA_BENCHMARKS.items()])
    def test_benchmarks_declare_payload_models(self, slug: str, cls: type[Benchmark]) -> None:
        assert issubclass(cls.task_payload_model, BaseModel), (
            f"Benchmark '{slug}' ({cls.__qualname__}) must declare a Pydantic task_payload_model."
        )

    @pytest.mark.parametrize("slug, cls", [*CORE_BENCHMARKS.items(), *DATA_BENCHMARKS.items()])
    def test_required_packages_are_plain_strings(self, slug: str, cls: type[Benchmark]) -> None:
        assert isinstance(cls.required_packages, list), (
            f"Benchmark '{slug}' ({cls.__qualname__}).required_packages must be a list."
        )
        assert all(isinstance(package, str) for package in cls.required_packages), (
            f"Benchmark '{slug}' ({cls.__qualname__}).required_packages must contain strings."
        )

    def test_data_benchmarks_with_package_deps_include_install_hint(self) -> None:
        for cls in DATA_BENCHMARKS.values():
            if cls.required_packages:
                assert cls.install_hint


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
