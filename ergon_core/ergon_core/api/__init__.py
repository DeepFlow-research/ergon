"""Object-first Ergon public API surface."""

from ergon_core.api.benchmark import Benchmark
from ergon_core.api.benchmark_deps import BenchmarkDeps
from ergon_core.api.criterion import Criterion
from ergon_core.api.errors import CriteriaCheckError, DependencyError
from ergon_core.api.evaluation_context import EvaluationContext
from ergon_core.api.evaluator import Evaluator, Rubric
from ergon_core.api.experiment import Experiment
from ergon_core.api.handles import ExperimentRunHandle, PersistedExperimentDefinition
from ergon_core.api.results import CriterionResult, TaskEvaluationResult, WorkerOutput
from ergon_core.api.task_types import BenchmarkTask, EmptyTaskPayload
from ergon_core.api.worker import Worker
from ergon_core.api.worker_context import WorkerContext
from ergon_core.api.worker_spec import WorkerSpec

__all__ = [
    "Benchmark",
    "BenchmarkDeps",
    "BenchmarkTask",
    "Criterion",
    "CriterionResult",
    "CriteriaCheckError",
    "DependencyError",
    "EvaluationContext",
    "Evaluator",
    "Experiment",
    "ExperimentRunHandle",
    "EmptyTaskPayload",
    "PersistedExperimentDefinition",
    "Rubric",
    "TaskEvaluationResult",
    "Worker",
    "WorkerContext",
    "WorkerOutput",
    "WorkerSpec",
]
