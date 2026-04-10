"""Smoke-test benchmark with multiple workflow variants.

Supports single, linear, parallel, and diamond DAG shapes to exercise
the full execution pipeline.
"""

from collections.abc import Mapping, Sequence
from typing import ClassVar

from h_arcane.api.benchmark import Benchmark
from h_arcane.api.task_types import BenchmarkTask

from arcane_builtins.benchmarks.smoke_test.tasks import (
    diamond_tasks,
    linear_tasks,
    parallel_tasks,
    single_task,
)

class SmokeTestBenchmark(Benchmark):
    type_slug: ClassVar[str] = "smoke-test"

    def __init__(
        self,
        *,
        workflow: str = "single",
        task_count: int = 2,
        limit: int | None = None,
    ) -> None:
        super().__init__(
            name="smoke-test",
            description=f"Smoke test benchmark ({workflow} workflow)",
        )
        self.workflow = workflow
        self.task_count = limit if limit is not None else task_count

    def build_instances(self) -> Mapping[str, Sequence[BenchmarkTask]]:
        _factories: dict[str, object] = {
            "single": single_task,
            "linear": linear_tasks,
            "parallel": parallel_tasks,
            "diamond": diamond_tasks,
        }
        factory = _factories.get(self.workflow)
        if factory is not None:
            return {"default": factory()}  # type: ignore[operator]

        tasks = [
            BenchmarkTask(
                task_key=f"task_{i}",
                instance_key="default",
                description=f"Smoke test task {i}",
                evaluator_binding_keys=("default",),
            )
            for i in range(self.task_count)
        ]
        return {"default": tasks}

    def evaluator_requirements(self) -> Sequence[str]:
        return ["default"]
