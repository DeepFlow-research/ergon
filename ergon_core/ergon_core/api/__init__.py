"""Object-first Ergon public API surface."""

from typing import TYPE_CHECKING

from ergon_core.api.benchmark import Benchmark
from ergon_core.api.benchmark_deps import BenchmarkDeps
from ergon_core.api.criterion import Criterion
from ergon_core.api.criterion_runtime import CommandResult, CriterionRuntime, SandboxResult
from ergon_core.api.errors import CriteriaCheckError, DependencyError
from ergon_core.api.evaluation_context import EvaluationContext
from ergon_core.api.evaluator import Evaluator, Rubric
from ergon_core.api.experiment import Experiment
from ergon_core.api.handles import ExperimentRunHandle, PersistedExperimentDefinition
from ergon_core.api.results import CriterionResult, TaskEvaluationResult, WorkerOutput
from ergon_core.api.task_types import BenchmarkTask, EmptyTaskPayload
from ergon_core.api.types import Tool
from ergon_core.api.worker import Worker
from ergon_core.api.worker_context import WorkerContext
from ergon_core.api.worker_spec import WorkerSpec

if TYPE_CHECKING:
    from ergon_core.api.run_resource import RunResourceKind, RunResourceView

__all__ = [
    "Benchmark",
    "BenchmarkDeps",
    "BenchmarkTask",
    "CommandResult",
    "Criterion",
    "CriterionResult",
    "CriteriaCheckError",
    "CriterionRuntime",
    "DependencyError",
    "EvaluationContext",
    "Evaluator",
    "Experiment",
    "ExperimentRunHandle",
    "EmptyTaskPayload",
    "PersistedExperimentDefinition",
    "Rubric",
    "RunResourceKind",
    "RunResourceView",
    "SandboxResult",
    "TaskEvaluationResult",
    "Tool",
    "Worker",
    "WorkerContext",
    "WorkerOutput",
    "WorkerSpec",
]


def __getattr__(name: str) -> object:
    if name in {"RunResourceKind", "RunResourceView"}:
        from ergon_core.api.run_resource import RunResourceKind, RunResourceView

        globals()["RunResourceKind"] = RunResourceKind
        globals()["RunResourceView"] = RunResourceView
        return globals()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
