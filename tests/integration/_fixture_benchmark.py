"""Minimal in-test benchmark fixture for lifecycle integration tests.

Replaces the deleted ``SmokeTestBenchmark(workflow="flat", task_count=N)``.
Produces ``task_count`` trivial tasks in a single instance, zero
dependencies between them -- enough to drive the orchestration
services (initialize -> prepare -> propagate -> finalize) without
pulling in any real benchmark loader.

Lives under a leading-underscore module name so pytest does not try to
collect it as a test file.
"""

from collections.abc import Mapping, Sequence
from typing import ClassVar

from ergon_core.api.benchmark import Benchmark
from ergon_core.api.task_types import BenchmarkTask


class LifecycleFixtureBenchmark(Benchmark):
    """Flat DAG of ``task_count`` independent tasks."""

    type_slug: ClassVar[str] = "lifecycle-fixture"

    def __init__(self, *, task_count: int = 2) -> None:
        super().__init__()
        self._task_count = task_count

    def build_instances(self) -> Mapping[str, Sequence[BenchmarkTask]]:
        tasks = [
            BenchmarkTask(
                task_key=f"lifecycle-task-{i}",
                instance_key="default",
                description=f"lifecycle fixture task {i}",
            )
            for i in range(self._task_count)
        ]
        return {"default": tasks}
