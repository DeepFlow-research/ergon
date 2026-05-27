"""Public benchmark authoring API."""

from ergon_core.api.benchmark.benchmark import Benchmark
from ergon_core.api.benchmark.task import EmptyTaskPayload, Task

__all__ = ["Benchmark", "Task", "EmptyTaskPayload"]
