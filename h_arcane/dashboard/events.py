"""Dashboard event contracts following InngestEventContract pattern.

These events are consumed by the Next.js dashboard for real-time visualization.
They are separate from orchestration events (task/*, workflow/*) to avoid interference.

All events use the "dashboard/" prefix.
"""

from typing import ClassVar

from h_arcane.core._internal.events.base import InngestEventContract


# =============================================================================
# Workflow Lifecycle Events (for Dashboard)
# =============================================================================


class DashboardWorkflowStartedEvent(InngestEventContract):
    """Emitted when execute_task() is called - for dashboard visualization."""

    name: ClassVar[str] = "dashboard/workflow.started"

    run_id: str
    experiment_id: str
    workflow_name: str
    task_tree: dict  # Full DAG structure for rendering
    started_at: str  # ISO format
    total_tasks: int
    total_leaf_tasks: int


class DashboardWorkflowCompletedEvent(InngestEventContract):
    """Emitted when workflow finishes - for dashboard visualization."""

    name: ClassVar[str] = "dashboard/workflow.completed"

    run_id: str
    status: str  # "completed" | "failed"
    completed_at: str
    duration_seconds: float
    final_score: float | None = None
    error: str | None = None


# =============================================================================
# Task Lifecycle Events (for Dashboard)
# =============================================================================


class DashboardTaskStatusChangedEvent(InngestEventContract):
    """Emitted on any task status transition - for dashboard visualization."""

    name: ClassVar[str] = "dashboard/task.status_changed"

    run_id: str
    task_id: str
    task_name: str
    parent_task_id: str | None = None
    old_status: str | None = None
    new_status: str  # pending | ready | running | completed | failed
    triggered_by: str | None = None
    timestamp: str
    assigned_worker_id: str | None = None
    assigned_worker_name: str | None = None


# =============================================================================
# Agent Action Events (for Dashboard)
# =============================================================================


class DashboardAgentActionStartedEvent(InngestEventContract):
    """Emitted when an agent begins a tool call - for dashboard action stream."""

    name: ClassVar[str] = "dashboard/agent.action_started"

    run_id: str
    task_id: str
    action_id: str
    worker_id: str
    worker_name: str
    action_type: str  # Tool name
    action_input: str  # JSON string of tool arguments
    timestamp: str


class DashboardAgentActionCompletedEvent(InngestEventContract):
    """Emitted when an agent completes a tool call - for dashboard action stream."""

    name: ClassVar[str] = "dashboard/agent.action_completed"

    run_id: str
    task_id: str
    action_id: str
    worker_id: str
    action_type: str
    action_output: str | None = None  # JSON string
    duration_ms: int
    success: bool
    error: str | None = None
    timestamp: str


# =============================================================================
# Resource Events (for Dashboard)
# =============================================================================


class DashboardResourcePublishedEvent(InngestEventContract):
    """Emitted when a task produces an output resource."""

    name: ClassVar[str] = "dashboard/resource.published"

    run_id: str
    task_id: str
    task_execution_id: str
    resource_id: str
    resource_name: str
    mime_type: str
    size_bytes: int
    preview_text: str | None = None
    file_path: str
    timestamp: str
