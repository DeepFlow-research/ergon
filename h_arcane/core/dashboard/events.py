"""Dashboard event contracts following InngestEventContract pattern.

These events are consumed by the Next.js dashboard for real-time visualization.
They are separate from orchestration events (task/*, workflow/*) to avoid interference.

All events use the "dashboard/" prefix.
UUIDs are used for internal IDs; they serialize to strings via model_dump(mode='json').
"""

from datetime import datetime
from typing import ClassVar
from uuid import UUID

from pydantic import BaseModel

from h_arcane.core._internal.events.base import InngestEventContract
from h_arcane.core._internal.task.schema import TaskTreeNode
from h_arcane.core.status import TaskStatus, TaskTrigger


# =============================================================================
# Workflow Lifecycle Events (for Dashboard)
# =============================================================================


class DashboardWorkflowStartedEvent(InngestEventContract):
    """Emitted when execute_task() is called - for dashboard visualization."""

    name: ClassVar[str] = "dashboard/workflow.started"

    run_id: UUID
    experiment_id: UUID
    workflow_name: str
    task_tree: TaskTreeNode  # Full DAG structure for rendering
    started_at: datetime
    total_tasks: int
    total_leaf_tasks: int


class DashboardWorkflowCompletedEvent(InngestEventContract):
    """Emitted when workflow finishes - for dashboard visualization."""

    name: ClassVar[str] = "dashboard/workflow.completed"

    run_id: UUID
    status: str  # "completed" | "failed"
    completed_at: datetime
    duration_seconds: float
    final_score: float | None = None
    error: str | None = None


# =============================================================================
# Task Lifecycle Events (for Dashboard)
# =============================================================================


class DashboardTaskStatusChangedEvent(InngestEventContract):
    """Emitted on any task status transition - for dashboard visualization."""

    name: ClassVar[str] = "dashboard/task.status_changed"

    run_id: UUID
    task_id: UUID
    task_name: str
    parent_task_id: UUID | None = None
    old_status: TaskStatus | None = None
    new_status: TaskStatus
    triggered_by: TaskTrigger | None = None
    timestamp: datetime
    assigned_worker_id: UUID | None = None
    assigned_worker_name: str | None = None


# =============================================================================
# Agent Action Events (for Dashboard)
# =============================================================================


class DashboardAgentActionStartedEvent(InngestEventContract):
    """Emitted when an agent begins a tool call - for dashboard action stream."""

    name: ClassVar[str] = "dashboard/agent.action_started"

    run_id: UUID
    task_id: UUID
    action_id: UUID
    worker_id: UUID
    worker_name: str
    action_type: str  # Tool name
    action_input: str  # JSON string of tool arguments
    timestamp: datetime


class DashboardAgentActionCompletedEvent(InngestEventContract):
    """Emitted when an agent completes a tool call - for dashboard action stream."""

    name: ClassVar[str] = "dashboard/agent.action_completed"

    run_id: UUID
    task_id: UUID
    action_id: UUID
    worker_id: UUID
    action_type: str
    action_output: str | None = None  # JSON string
    duration_ms: int | None = None
    success: bool
    error: str | None = None
    timestamp: datetime


# =============================================================================
# Resource Events (for Dashboard)
# =============================================================================


class DashboardResourcePublishedEvent(InngestEventContract):
    """Emitted when a task produces an output resource."""

    name: ClassVar[str] = "dashboard/resource.published"

    run_id: UUID
    task_id: UUID
    task_execution_id: UUID
    resource_id: UUID
    resource_name: str
    mime_type: str
    size_bytes: int
    file_path: str
    timestamp: datetime


# =============================================================================
# Sandbox Lifecycle Events (for Dashboard)
# =============================================================================


class DashboardSandboxCreatedEvent(InngestEventContract):
    """Emitted when an E2B sandbox is created for a task."""

    name: ClassVar[str] = "dashboard/sandbox.created"

    run_id: UUID
    task_id: UUID
    sandbox_id: str  # E2B sandbox ID (not a UUID)
    template: str | None = None  # E2B template name if used
    timeout_minutes: int
    timestamp: datetime


class DashboardSandboxCommandEvent(InngestEventContract):
    """Emitted when a command is executed in a sandbox."""

    name: ClassVar[str] = "dashboard/sandbox.command"

    task_id: UUID
    sandbox_id: str  # E2B sandbox ID (not a UUID)
    command: str
    stdout: str | None = None
    stderr: str | None = None
    exit_code: int | None = None
    duration_ms: int | None = None
    timestamp: datetime


class DashboardSandboxClosedEvent(InngestEventContract):
    """Emitted when a sandbox is terminated."""

    name: ClassVar[str] = "dashboard/sandbox.closed"

    task_id: UUID
    sandbox_id: str  # E2B sandbox ID (not a UUID)
    reason: str  # "completed" | "timeout" | "error" | "cleanup"
    timestamp: datetime


# =============================================================================
# Communication + Evaluation Events (for Dashboard)
# =============================================================================


class DashboardCommunicationMessage(BaseModel):
    id: UUID
    thread_id: UUID
    run_id: UUID
    task_id: UUID | None = None
    thread_topic: str
    from_agent_id: str
    to_agent_id: str
    content: str
    sequence_num: int
    created_at: datetime


class DashboardCommunicationThread(BaseModel):
    id: UUID
    run_id: UUID
    task_id: UUID | None = None
    topic: str
    agent_a_id: str
    agent_b_id: str
    created_at: datetime
    updated_at: datetime
    messages: list[DashboardCommunicationMessage]


class DashboardThreadMessageCreatedEvent(InngestEventContract):
    """Emitted when a thread gains a new message."""

    name: ClassVar[str] = "dashboard/thread.message_created"

    run_id: UUID
    thread: DashboardCommunicationThread
    message: DashboardCommunicationMessage


class DashboardEvaluationCriterion(BaseModel):
    id: UUID
    stage_num: int
    stage_name: str
    criterion_num: int
    criterion_type: str
    criterion_description: str
    score: float
    max_score: float
    feedback: str
    evaluation_input: str
    error: dict | None = None
    evaluated_action_ids: list[str]
    evaluated_resource_ids: list[str]


class DashboardTaskEvaluation(BaseModel):
    id: UUID
    run_id: UUID
    task_id: UUID | None = None
    total_score: float
    max_score: float
    normalized_score: float
    stages_evaluated: int
    stages_passed: int
    failed_gate: str | None = None
    created_at: datetime
    criterion_results: list[DashboardEvaluationCriterion]


class DashboardTaskEvaluationUpdatedEvent(InngestEventContract):
    """Emitted when task evaluation truth becomes available or changes."""

    name: ClassVar[str] = "dashboard/task.evaluation_updated"

    run_id: UUID
    task_id: UUID | None = None
    evaluation: DashboardTaskEvaluation
