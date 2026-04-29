"""Inngest-facing aliases for application job contracts."""

from ergon_core.core.application.jobs.models import (
    EvaluateTaskRunRequest,
    EvaluateTaskRunResult,
    EvaluatorsResult,
    PersistOutputsRequest,
    PersistOutputsResult,
    RunCleanupResult,
    SandboxReadyResult,
    SandboxSetupRequest,
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
    "EvaluateTaskRunRequest",
    "EvaluateTaskRunResult",
    "EvaluatorsResult",
    "InngestEvent",
    "PersistOutputsRequest",
    "PersistOutputsResult",
    "RunCleanupResult",
    "SandboxReadyResult",
    "SandboxSetupRequest",
    "TaskExecuteResult",
    "TaskPropagateResult",
    "WorkerExecuteRequest",
    "WorkerExecuteResult",
    "WorkflowCompleteResult",
    "WorkflowFailedResult",
    "WorkflowStartResult",
]
