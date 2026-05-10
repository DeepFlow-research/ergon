"""Contract: every registered benchmark declares onboarding_deps."""

from collections.abc import AsyncGenerator
from typing import ClassVar

import pytest
from ergon_builtins.registry_core import BENCHMARKS as CORE_BENCHMARKS
from ergon_core.api import Sandbox, Worker, WorkerContext, WorkerOutput
from ergon_core.api.benchmark import Benchmark, BenchmarkRequirements, EmptyTaskPayload, Task
from pydantic import BaseModel, ValidationError


class _Sandbox(Sandbox):
    async def provision(self) -> None:
        return None


class _Worker(Worker):
    type_slug: ClassVar[str] = "benchmark-contract-worker"

    async def execute(
        self,
        task: Task,
        *,
        context: WorkerContext,
        sandbox: Sandbox,
    ) -> AsyncGenerator[WorkerOutput, None]:
        yield WorkerOutput(output="", success=True)


def _task_bindings() -> dict[str, object]:
    return {"worker": _Worker(name="worker", model=None), "sandbox": _Sandbox()}


def _require_onboarding_deps(slug: str, cls: type[Benchmark]) -> BenchmarkRequirements:
    try:
        deps = cls.onboarding_deps
    except AttributeError as exc:
        pytest.fail(
            f"Benchmark '{slug}' ({cls.__qualname__}) is missing 'onboarding_deps'. "
            "Add 'onboarding_deps: ClassVar[BenchmarkRequirements] = BenchmarkRequirements(...)' "
            "to the class body.",
        )
        raise AssertionError from exc
    assert isinstance(deps, BenchmarkRequirements), (
        f"Benchmark '{slug}' ({cls.__qualname__}).onboarding_deps is not a "
        f"BenchmarkRequirements instance; got {type(deps)!r}."
    )
    return deps


class TestBenchmarkOnboardingDepsContract:
    """Every benchmark in both registries must declare onboarding_deps."""

    def test_core_benchmarks_have_onboarding_deps(self) -> None:
        for slug, cls in CORE_BENCHMARKS.items():
            _require_onboarding_deps(slug, cls)

    def test_data_benchmarks_have_onboarding_deps(self) -> None:
        pytest.importorskip("datasets", reason="ergon-builtins[data] not installed")
        # reason: registry_data imports optional dataset-backed benchmarks.
        from ergon_builtins.registry_data import BENCHMARKS

        for slug, cls in BENCHMARKS.items():
            _require_onboarding_deps(slug, cls)

    def test_core_benchmarks_declare_payload_models(self) -> None:
        for slug, cls in CORE_BENCHMARKS.items():
            assert issubclass(cls.task_payload_model, BaseModel), (
                f"Benchmark '{slug}' ({cls.__qualname__}) must declare a "
                "Pydantic task_payload_model."
            )

    def test_data_benchmarks_declare_payload_models(self) -> None:
        pytest.importorskip("datasets", reason="ergon-builtins[data] not installed")
        # reason: registry_data imports optional dataset-backed benchmarks.
        from ergon_builtins.registry_data import BENCHMARKS

        for slug, cls in BENCHMARKS.items():
            assert issubclass(cls.task_payload_model, BaseModel), (
                f"Benchmark '{slug}' ({cls.__qualname__}) must declare a "
                "Pydantic task_payload_model."
            )

    def test_onboarding_deps_is_frozen(self) -> None:
        """BenchmarkRequirements instances must be immutable (frozen=True via attribute access)."""
        for slug, cls in CORE_BENCHMARKS.items():
            deps = cls.onboarding_deps
            with pytest.raises(ValidationError):
                setattr(deps, "e2b", not deps.e2b)

    def test_known_e2b_benchmarks(self) -> None:
        # ``smoke-test`` and ``researchrubrics-smoke`` benchmarks retired
        # alongside the canonical-smoke refactor.
        assert CORE_BENCHMARKS["minif2f"].onboarding_deps.e2b is True
        assert CORE_BENCHMARKS["swebench-verified"].onboarding_deps.e2b is True


class TestBenchmarkSubclassEnforcement:
    def test_base_class_does_not_validate_subclasses_at_import_time(self) -> None:
        class LocalBenchmark(Benchmark):
            type_slug = "local-test"

            def build_instances(self) -> dict[str, list[Task[BaseModel]]]:
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
            **_task_bindings(),
            task_payload=payload,
        )

        assert task.task_payload is payload

    def test_plain_dict_payload_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Task(
                task_slug="task",
                instance_key="default",
                description="desc",
                **_task_bindings(),
                task_payload={"loose": "dict"},
            )
