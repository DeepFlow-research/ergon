"""Service DTOs for task orchestration and workflow finalization."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel

from h_arcane.core._internal.task.schema import TaskTreeNode


class PrepareTaskExecutionCommand(BaseModel):
    """Inputs required to prepare a task execution."""

    run_id: UUID
    experiment_id: UUID
    task_id: UUID


class PreparedTaskExecution(BaseModel):
    """Prepared task execution data for the orchestration runner."""

    run_id: UUID
    experiment_id: UUID
    task_id: UUID
    task_name: str
    parent_task_id: UUID | None = None
    task_description: str
    benchmark_name: str
    max_questions: int
    input_resource_ids: list[UUID]
    execution_id: UUID | None = None
    skipped: bool = False
    skip_reason: str | None = None


class FinalizeTaskExecutionCommand(BaseModel):
    """Inputs required to persist a successful task execution."""

    execution_id: UUID
    output_text: str | None = None
    output_resource_ids: list[UUID]


class FailTaskExecutionCommand(BaseModel):
    """Inputs required to persist a failed task execution."""

    execution_id: UUID
    run_id: UUID
    task_id: UUID
    error_message: str


class TaskDescriptor(BaseModel):
    """Task metadata used by orchestration follow-up steps."""

    task_id: UUID
    task_name: str
    parent_task_id: UUID | None = None


class InitializeWorkflowCommand(BaseModel):
    """Inputs required to initialize a workflow run."""

    run_id: UUID
    experiment_id: UUID


class InitializedWorkflow(BaseModel):
    """Prepared workflow initialization result for the runner."""

    run_id: UUID
    experiment_id: UUID
    workflow_name: str
    task_tree: TaskTreeNode
    dependency_count: int
    evaluator_count: int
    total_tasks: int
    total_leaf_tasks: int
    pending_tasks: list[TaskDescriptor]
    initial_ready_tasks: list[TaskDescriptor]


class PropagateTaskCompletionCommand(BaseModel):
    """Inputs required to advance workflow state after task completion."""

    run_id: UUID
    experiment_id: UUID
    task_id: UUID
    execution_id: UUID


class WorkflowTerminalState(str, Enum):
    """Workflow terminal classification after a propagation step."""

    NONE = "none"
    COMPLETED = "completed"
    FAILED = "failed"


class PropagationResult(BaseModel):
    """Propagation result returned to the orchestration runner."""

    run_id: UUID
    experiment_id: UUID
    completed_task_id: UUID
    ready_tasks: list[TaskDescriptor]
    workflow_terminal_state: WorkflowTerminalState


class FinalizeWorkflowCommand(BaseModel):
    """Inputs required to finalize a workflow run."""

    run_id: UUID


class FinalizedWorkflowResult(BaseModel):
    """Result returned by workflow finalization service."""

    run_id: UUID
    final_score: float | None = None
    normalized_score: float | None = None
    evaluators_count: int = 0


@dataclass(frozen=True)
class RunCompletionData:
    """All data needed to complete a run atomically."""

    completed_at: datetime
    final_score: float | None
    normalized_score: float | None
    total_cost_usd: float
    output_text: str | None
    execution_result: dict
