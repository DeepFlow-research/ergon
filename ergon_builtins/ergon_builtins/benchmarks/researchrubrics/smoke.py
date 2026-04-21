"""ResearchRubrics smoke benchmark: one task, stub worker, stub criterion.

Used by the E2B smoke test in CI to validate the full sandbox -> publisher ->
RunResource -> criterion pipeline without LLM calls or HuggingFace datasets.
"""

from collections.abc import Mapping, Sequence
from typing import ClassVar

from ergon_core.api.benchmark import Benchmark
from ergon_core.api.benchmark_deps import BenchmarkDeps
from ergon_core.api.task_types import BenchmarkTask
from ergon_core.api.template_spec import NoSetup, NoSetupSentinel, TemplateSpec


class ResearchRubricsSmokeTestBenchmark(Benchmark):
    """Single-task benchmark for real-E2B smoke testing."""

    type_slug: ClassVar[str] = "researchrubrics-smoke"
    onboarding_deps: ClassVar[BenchmarkDeps] = BenchmarkDeps()
    template_spec: ClassVar[TemplateSpec | NoSetupSentinel] = NoSetup

    def __init__(
        self,
        *,
        limit: int | None = None,
    ) -> None:
        super().__init__(
            name="researchrubrics-smoke",
            description=(
                "Smoke test for the researchrubrics pipeline. "
                "One task, stub worker, stub criterion."
            ),
        )
        self._limit = limit

    def build_instances(self) -> Mapping[str, Sequence[BenchmarkTask]]:
        tasks = [
            BenchmarkTask(
                task_key="smoke-research-001",
                instance_key="default",
                description=(
                    "Write a brief research report about E2B sandbox integration testing."
                ),
                evaluator_binding_keys=("default",),
            ),
        ]
        if self._limit is not None:
            tasks = tasks[: self._limit]
        return {"default": tasks}

    def evaluator_requirements(self) -> Sequence[str]:
        return ("default",)
