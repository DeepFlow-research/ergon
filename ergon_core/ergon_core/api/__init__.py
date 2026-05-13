"""Beginner-facing Ergon authoring API surface."""

from ergon_core.api.benchmark import (
    Benchmark,
    BenchmarkRequirements,
    EmptyTaskPayload,
    Task,
    TaskSpec,
)
from ergon_core.api.criterion import (
    Criterion,
    CriterionContext,
    CriterionEvidence,
    CriterionOutcome,
    EvidenceMessage,
    ScoreScale,
)
from ergon_core.api.errors import CriterionCheckError, SandboxNotLiveError
from ergon_core.api.registry import ComponentRegistry, registry
from ergon_core.api.rubric import Evaluator, Rubric, TaskEvaluationResult
from ergon_core.api.sandbox import Sandbox, SandboxRuntime
from ergon_core.api.worker import Worker, WorkerContext, WorkerOutput, WorkerStreamItem

# Resolve forward references on ``Task`` now that ``Worker``,
# ``Sandbox``, and ``Evaluator`` are all importable. ``Task`` annotates
# its object-bound fields with string forward refs (the natural import
# graph runs the other way — Worker/Sandbox/Evaluator each import
# ``Task``), so Pydantic can't resolve them at the class-definition
# site. This package's load completes after every component module, so
# rebuilding here is the canonical late-binding point.
Task.model_rebuild()

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
    "Evaluator",
    "EvidenceMessage",
    "Rubric",
    "Sandbox",
    "SandboxNotLiveError",
    "SandboxRuntime",
    "ScoreScale",
    "Task",
    "TaskSpec",
    "TaskEvaluationResult",
    "Worker",
    "WorkerContext",
    "WorkerOutput",
    "WorkerStreamItem",
    "registry",
]
