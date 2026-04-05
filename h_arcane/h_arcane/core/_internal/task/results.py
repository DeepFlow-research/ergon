"""Result types for task Inngest functions.

These are the typed return values for all task-related Inngest functions.
Used as output_type= in function decorators for type safety.

Organized by:
- Workflow results (workflow_start, workflow_complete, workflow_failed)
- Task orchestrator results (task_execute, task_propagate)
- Child function results (sandbox_setup, worker_execute, persist_outputs)
- Internal step results (used within functions)
- Data transfer objects (RunCompletionData in dto, etc.)
"""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel


# =============================================================================
# Workflow Results
# =============================================================================


class WorkflowStartResult(BaseModel):
    """Result of workflow_start function."""

    run_id: UUID
    dependencies_created: int
    evaluators_created: int
    initial_ready_tasks: int


class WorkflowCompleteResult(BaseModel):
    """Result of workflow_complete function."""

    run_id: UUID
    status: Literal["completed"] = "completed"
    final_score: float | None = None
    normalized_score: float | None = None
    evaluators_count: int = 0


class WorkflowFailedResult(BaseModel):
    """Result of workflow_failed function."""

    run_id: UUID
    status: Literal["failed"] = "failed"
    error: str


# =============================================================================
# Task Orchestrator Results
# =============================================================================


class TaskExecuteResult(BaseModel):
    """Result of task_execute orchestrator function."""

    run_id: UUID
    task_id: UUID
    execution_id: UUID | None = None
    success: bool
    skipped: bool = False
    skip_reason: str | None = None
    outputs_count: int = 0
    questions_asked: int = 0
    error: str | None = None


class TaskPropagateResult(BaseModel):
    """Result of task_propagate function."""

    run_id: UUID
    task_id: UUID
    newly_ready_tasks: int
    workflow_complete: bool
    workflow_failed: bool


# =============================================================================
# Child Function Results
# =============================================================================


class SandboxReadyResult(BaseModel):
    """Result of sandbox_setup child function."""

    sandbox_id: str
    output_dir: str


class WorkerExecuteResult(BaseModel):
    """Result of worker_execute child function."""

    success: bool
    output_text: str | None = None
    questions_asked: int = 0
    error: str | None = None


class PersistOutputsResult(BaseModel):
    """Result of persist_outputs child function."""

    output_resource_ids: list[UUID]
    outputs_count: int


# =============================================================================
# Internal Step Results (used within functions, not as function outputs)
# =============================================================================


class DagInitResult(BaseModel):
    """Result of initialize-dag step (dependencies + evaluators)."""

    dependency_count: int
    evaluator_count: int


class ReadyTaskIdsResult(BaseModel):
    """Result of steps that identify ready tasks."""

    ready_task_ids: list[UUID]


