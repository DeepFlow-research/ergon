"""Beginner-facing Ergon authoring API surface."""

from ergon_core.api.task import EmptyTaskPayload, Task
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
    DependencyError,
    SandboxKindMismatch,
    SandboxNotLiveError,
)
from ergon_core.api.experiment import (
    Environment,
    Experiment,
    ExperimentSubmitResult,
    PersistedExperiment,
    RandomSampler,
    Sample,
    Sampler,
    SamplingContext,
)
from ergon_core.api.rubric import Evaluator, Rubric, TaskEvaluationResult
from ergon_core.api.sandbox import Sandbox, SandboxRuntime
from ergon_core.api.worker import (
    AwaitCompletionNotSupportedError,
    SpawnedTaskHandle,
    Worker,
    WorkerContext,
    WorkerOutput,
    WorkerStreamItem,
)

# Resolve forward references on ``Task`` now that ``Worker``,
# ``Sandbox``, and ``Evaluator`` are all importable. ``Task`` annotates
# its object-bound fields with string forward refs (the natural import
# graph runs the other way — Worker/Sandbox/Evaluator each import
# ``Task``), so Pydantic can't resolve them at the class-definition
# site. This package's load completes after every component module, so
# rebuilding here is the canonical late-binding point.
Task.model_rebuild()

__all__ = [
    "AwaitCompletionNotSupportedError",
    "ContainmentViolation",
    "Criterion",
    "CriterionCheckError",
    "CriterionContext",
    "CriterionEvidence",
    "CriterionOutcome",
    "DependencyError",
    "EmptyTaskPayload",
    "Environment",
    "Experiment",
    "ExperimentSubmitResult",
    "PersistedExperiment",
    "Evaluator",
    "EvidenceMessage",
    "RandomSampler",
    "Rubric",
    "Sample",
    "Sandbox",
    "SandboxKindMismatch",
    "SandboxNotLiveError",
    "SandboxRuntime",
    "ScoreScale",
    "Sampler",
    "SamplingContext",
    "SpawnedTaskHandle",
    "Task",
    "TaskEvaluationResult",
    "Worker",
    "WorkerContext",
    "WorkerOutput",
    "WorkerStreamItem",
]
