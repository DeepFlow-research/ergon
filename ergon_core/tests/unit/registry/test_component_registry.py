import pytest

from ergon_core.api import Benchmark, Rubric, Worker
from ergon_core.api.registry import ComponentRegistry
from ergon_core.core.infrastructure.sandbox.manager import BaseSandboxManager


class ExampleWorker(Worker):
    type_slug = "example-worker"


class ReplacementWorker(Worker):
    type_slug = "example-worker"


class ExampleBenchmark(Benchmark):
    type_slug = "example-benchmark"


class ExampleRubric(Rubric):
    type_slug = "example-rubric"


class ExampleSandboxManager(BaseSandboxManager):
    pass


def test_registers_components_by_explicit_or_type_slug() -> None:
    registry = ComponentRegistry()

    registry.register_worker(ExampleWorker.type_slug, ExampleWorker)
    registry.register_benchmark(ExampleBenchmark)
    registry.register_evaluator(ExampleRubric)
    registry.register_sandbox_manager("example-benchmark", ExampleSandboxManager)

    assert registry.require_worker("example-worker") is ExampleWorker
    assert registry.require_benchmark("example-benchmark") is ExampleBenchmark
    assert registry.require_evaluator("example-rubric") is ExampleRubric
    assert registry.sandbox_managers["example-benchmark"] is ExampleSandboxManager


def test_duplicate_slug_rejects_different_object() -> None:
    registry = ComponentRegistry()
    registry.register_worker("example-worker", ExampleWorker)

    with pytest.raises(ValueError, match="Duplicate worker slug 'example-worker'"):
        registry.register_worker("example-worker", ReplacementWorker)


def test_duplicate_slug_allows_idempotent_registration() -> None:
    registry = ComponentRegistry()
    registry.register_worker("example-worker", ExampleWorker)
    registry.register_worker("example-worker", ExampleWorker)

    assert registry.require_worker("example-worker") is ExampleWorker


def test_unknown_slug_error_lists_registered_values() -> None:
    registry = ComponentRegistry()
    registry.register_worker("example-worker", ExampleWorker)

    with pytest.raises(
        ValueError,
        match="Unknown worker slug 'missing-worker'; registered workers: example-worker",
    ):
        registry.require_worker("missing-worker")
