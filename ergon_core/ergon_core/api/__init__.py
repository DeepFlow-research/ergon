"""Beginner-facing Ergon authoring API surface."""

from ergon_core.api.benchmark import (
    Benchmark,
    BenchmarkRequirements,
    EmptyTaskPayload,
    Task,
)
from ergon_core.api.criterion import (
    Criterion,
    CriterionContext,
    CriterionEvidence,
    CriterionOutcome,
    EvidenceMessage,
    ScoreScale,
)
from ergon_core.api.errors import (
    ContainmentViolation,
    CriterionCheckError,
    SandboxKindMismatch,
    SandboxNotLiveError,
    TaskNotMaterializedError,
)
from ergon_core.api.experiment import Experiment
from ergon_core.api.rubric import Evaluator, Rubric, TaskEvaluationResult, WeightedCriterion
from ergon_core.api.sandbox import Sandbox, SandboxRuntime
from ergon_core.api.worker import Worker, WorkerContext, WorkerOutput, WorkerStreamItem

__all__ = [
    "Benchmark",
    "BenchmarkRequirements",
    "ContainmentViolation",
    "Criterion",
    "CriterionCheckError",
    "CriterionContext",
    "CriterionEvidence",
    "CriterionOutcome",
    "EmptyTaskPayload",
    "Evaluator",
    "EvidenceMessage",
    "Experiment",
    "Rubric",
    "Sandbox",
    "SandboxKindMismatch",
    "SandboxNotLiveError",
    "SandboxRuntime",
    "ScoreScale",
    "Task",
    "TaskEvaluationResult",
    "TaskNotMaterializedError",
    "WeightedCriterion",
    "Worker",
    "WorkerContext",
    "WorkerOutput",
    "WorkerStreamItem",
]
