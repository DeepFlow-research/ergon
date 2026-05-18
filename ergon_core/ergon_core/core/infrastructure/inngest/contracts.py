"""Inngest-facing aliases for application job contracts."""

from ergon_core.core.application.jobs.models import (
    EvaluateTaskRunResult,
    EvaluatorsResult,
    PersistOutputsRequest,
    PersistOutputsResult,
    RunCleanupResult,
    SandboxReadyResult,
    SandboxSetupRequest,
    TaskEvaluateRequest,
    TaskExecuteResult,
    TaskPropagateResult,
    WorkerExecuteRequest,
    WorkerExecuteResult,
    WorkflowCompleteResult,
    WorkflowFailedResult,
    WorkflowStartResult,
)
from ergon_core.core.infrastructure.inngest.client import InngestEvent

__all__ = [
    "EvaluateTaskRunResult",
    "EvaluatorsResult",
    "InngestEvent",
    "PersistOutputsRequest",
    "PersistOutputsResult",
    "RunCleanupResult",
    "SandboxReadyResult",
    "SandboxSetupRequest",
    "TaskEvaluateRequest",
    "TaskExecuteResult",
    "TaskPropagateResult",
    "WorkerExecuteRequest",
    "WorkerExecuteResult",
    "WorkflowCompleteResult",
    "WorkflowFailedResult",
    "WorkflowStartResult",
]
