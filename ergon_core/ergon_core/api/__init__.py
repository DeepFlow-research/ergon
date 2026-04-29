"""Beginner-facing Ergon authoring API surface."""

from ergon_core.api.benchmark import Benchmark, BenchmarkRequirements, EmptyTaskPayload, Task
from ergon_core.api.criterion import (
    Criterion,
    CriterionContext,
    CriterionEvidence,
    CriterionOutcome,
    EvidenceMessage,
    ScoreScale,
)
from ergon_core.api.errors import CriterionCheckError
from ergon_core.api.registry import ComponentRegistry, WorkerFactory, registry
from ergon_core.api.rubric import Rubric, TaskEvaluationResult
from ergon_core.api.worker import Worker, WorkerContext, WorkerOutput, WorkerStreamItem

__all__ = [
    "Benchmark",
    "BenchmarkRequirements",
    "ComponentRegistry",
    "Criterion",
    "CriterionCheckError",
    "CriterionContext",
    "CriterionEvidence",
    "CriterionOutcome",
    "EmptyTaskPayload",
    "EvidenceMessage",
    "Rubric",
    "ScoreScale",
    "Task",
    "TaskEvaluationResult",
    "Worker",
    "WorkerContext",
    "WorkerFactory",
    "WorkerOutput",
    "WorkerStreamItem",
    "registry",
]
