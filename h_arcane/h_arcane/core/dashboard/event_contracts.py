"""Dashboard event contracts for real-time UI updates via Inngest.

Every contract here must match the corresponding Zod schema in
arcane-dashboard/src/lib/contracts/events.ts exactly.
"""

from datetime import datetime
from typing import Any, ClassVar
from uuid import UUID

from h_arcane.core.runtime.events.base import InngestEventContract

# ---------------------------------------------------------------------------
# Nested models used inside workflow.started
# ---------------------------------------------------------------------------

class TaskTreeNode(InngestEventContract):
    """Recursive task tree node embedded in workflow.started."""

    name: ClassVar[str] = "__embedded__"

    id: str
    name_field: str  # serialized as "name" via alias below
    status: str
    is_leaf: bool
    children: list["TaskTreeNode"] = []

    model_config = {"extra": "allow", "populate_by_name": True}

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:  # slopcop: ignore[no-typing-any]
        d = super().model_dump(**kwargs)
        d["name"] = d.pop("name_field", "")
        return d


TaskTreeNode.model_rebuild()

# ---------------------------------------------------------------------------
# Workflow-level events
# ---------------------------------------------------------------------------

class DashboardWorkflowStartedEvent(InngestEventContract):
    name: ClassVar[str] = "dashboard/workflow.started"

    run_id: UUID
    experiment_id: UUID
    workflow_name: str
    task_tree: dict[str, Any]  # slopcop: ignore[no-typing-any]
    started_at: datetime
    total_tasks: int
    total_leaf_tasks: int

class DashboardWorkflowCompletedEvent(InngestEventContract):
    name: ClassVar[str] = "dashboard/workflow.completed"

    run_id: UUID
    status: str
    completed_at: datetime
    duration_seconds: float
    final_score: float | None = None
    error: str | None = None

# ---------------------------------------------------------------------------
# Task-level events
# ---------------------------------------------------------------------------

class DashboardTaskStatusChangedEvent(InngestEventContract):
    name: ClassVar[str] = "dashboard/task.status_changed"

    run_id: UUID
    task_id: UUID
    task_name: str
    parent_task_id: UUID | None = None
    old_status: str | None = None
    new_status: str
    triggered_by: str | None = None
    timestamp: datetime
    assigned_worker_id: UUID | None = None
    assigned_worker_name: str | None = None

class DashboardTaskEvaluationUpdatedEvent(InngestEventContract):
    """Embeds the full RunTaskEvaluationDto (camelCase) as `evaluation`."""

    name: ClassVar[str] = "dashboard/task.evaluation_updated"

    run_id: UUID
    task_id: UUID | None = None
    evaluation: dict[str, Any]  # slopcop: ignore[no-typing-any]

# ---------------------------------------------------------------------------
# Agent action events
# ---------------------------------------------------------------------------

class DashboardAgentActionStartedEvent(InngestEventContract):
    name: ClassVar[str] = "dashboard/agent.action_started"

    run_id: UUID
    task_id: UUID
    action_id: str
    worker_id: UUID
    worker_name: str
    action_type: str
    action_input: str
    timestamp: datetime

class DashboardAgentActionCompletedEvent(InngestEventContract):
    name: ClassVar[str] = "dashboard/agent.action_completed"

    run_id: UUID
    task_id: UUID
    action_id: str
    worker_id: UUID
    action_type: str
    action_output: str | None = None
    duration_ms: int
    success: bool
    error: str | None = None
    timestamp: datetime

# ---------------------------------------------------------------------------
# Resource events
# ---------------------------------------------------------------------------

class DashboardResourcePublishedEvent(InngestEventContract):
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

# ---------------------------------------------------------------------------
# Sandbox events
# ---------------------------------------------------------------------------

class DashboardSandboxCreatedEvent(InngestEventContract):
    name: ClassVar[str] = "dashboard/sandbox.created"

    run_id: UUID
    task_id: UUID
    sandbox_id: str
    template: str | None = None
    timeout_minutes: int
    timestamp: datetime

class DashboardSandboxCommandEvent(InngestEventContract):
    name: ClassVar[str] = "dashboard/sandbox.command"

    task_id: UUID
    sandbox_id: str
    command: str
    stdout: str | None = None
    stderr: str | None = None
    exit_code: int | None = None
    duration_ms: int | None = None
    timestamp: datetime

class DashboardSandboxClosedEvent(InngestEventContract):
    name: ClassVar[str] = "dashboard/sandbox.closed"

    task_id: UUID
    sandbox_id: str
    reason: str
    timestamp: datetime

# ---------------------------------------------------------------------------
# Thread / messaging events
# ---------------------------------------------------------------------------

class DashboardThreadMessageCreatedEvent(InngestEventContract):
    """Embeds full RunCommunicationThreadDto + RunCommunicationMessageDto (camelCase)."""

    name: ClassVar[str] = "dashboard/thread.message_created"

    run_id: UUID
    thread: dict[str, Any]  # slopcop: ignore[no-typing-any]
    message: dict[str, Any]  # slopcop: ignore[no-typing-any]

# ---------------------------------------------------------------------------
# Cohort events
# ---------------------------------------------------------------------------

class CohortUpdatedEvent(InngestEventContract):
    name: ClassVar[str] = "dashboard/cohort.updated"

    cohort_id: UUID
    summary: dict[str, Any]  # slopcop: ignore[no-typing-any]

# ---------------------------------------------------------------------------
# Generation turn events (RL observability)
# ---------------------------------------------------------------------------

class DashboardGenerationTurnEvent(InngestEventContract):
    """Emitted after each model generation turn for live dashboard streaming.

    Carries the convenience fields only (no raw_request / raw_response /
    logprobs to keep the event payload small).  The dashboard can fetch
    full details via ``GET /runs/{run_id}/generations``.
    """

    name: ClassVar[str] = "dashboard/generation.turn_completed"

    run_id: UUID
    task_execution_id: UUID
    worker_binding_key: str
    worker_name: str
    turn_index: int
    response_text: str | None = None
    tool_calls: list[dict[str, Any]] | None = None  # slopcop: ignore[no-typing-any]
    policy_version: str | None = None
