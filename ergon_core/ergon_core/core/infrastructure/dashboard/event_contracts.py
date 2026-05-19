"""Dashboard event contracts for real-time UI updates via Inngest.

Every contract here must match the corresponding Zod schema in
ergon-dashboard/src/generated/events/*.ts — the latter is generated from
these models via scripts/export_contract_schemas.py +
json-schema-to-zod (see package.json ``generate:contracts``).  Any
change here that isn't regenerated will fail the CI drift check.
"""

from datetime import datetime
from typing import ClassVar
from uuid import UUID

from ergon_core.core.application.communication.models import (
    RunCommunicationMessageDto,
    RunCommunicationThreadDto,
)
from ergon_core.core.application.read_models.models import (
    RunTaskEvaluationDto,
)
from ergon_core.core.shared.context_parts import ContextEventType, ContextPartChunkLog
from ergon_core.core.application.runtime.status import NodeStatus
from ergon_core.core.application.events.base import InngestEventContract
from ergon_core.core.application.read_models.models import CohortSummaryDto
from ergon_core.core.application.graph.models import GraphMutationRecordDto
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Nested models used inside workflow.started
# ---------------------------------------------------------------------------


class WorkerRef(BaseModel):
    """Reference to an ``ExperimentDefinitionWorker`` row as seen by the
    dashboard — matches the Zod ``WorkerRefSchema``."""

    model_config = {"frozen": True}

    id: str
    name: str
    type: str


class TaskTreeNode(BaseModel):
    """Recursive task tree node embedded in workflow.started.

    Shape matches the dashboard Zod ``TaskTreeNodeSchema``.  Built from
    ``RunGraphNode`` + ``RunGraphEdge`` + ``ExperimentDefinitionWorker``
    at emit time; see ``start_workflow._build_task_tree_for_run``.
    """

    model_config = {"frozen": True}

    id: str
    name: str
    description: str
    status: NodeStatus
    level: int
    assigned_worker_slug: str | None = None
    assigned_to: WorkerRef
    children: list["TaskTreeNode"] = []
    depends_on: list[str] = []
    is_leaf: bool
    resources: list[str] = []
    parent_id: str | None = None


TaskTreeNode.model_rebuild()

# ---------------------------------------------------------------------------
# Workflow-level events
# ---------------------------------------------------------------------------


class DashboardWorkflowStartedEvent(InngestEventContract):
    name: ClassVar[str] = "dashboard/workflow.started"

    run_id: UUID
    definition_id: UUID
    workflow_name: str
    task_tree: TaskTreeNode
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
    old_status: NodeStatus | None = None
    new_status: NodeStatus
    triggered_by: str | None = None
    timestamp: datetime
    assigned_worker_id: UUID | None = None
    assigned_worker_slug: str | None = None


class DashboardTaskEvaluationUpdatedEvent(InngestEventContract):
    """Embeds the full RunTaskEvaluationDto as ``evaluation``."""

    name: ClassVar[str] = "dashboard/task.evaluation_updated"

    run_id: UUID
    task_id: UUID
    evaluation: RunTaskEvaluationDto


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

    run_id: UUID
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
    """Embeds full RunCommunicationThreadDto + RunCommunicationMessageDto."""

    name: ClassVar[str] = "dashboard/thread.message_created"

    run_id: UUID
    thread: RunCommunicationThreadDto
    message: RunCommunicationMessageDto


# ---------------------------------------------------------------------------
# Cohort events
# ---------------------------------------------------------------------------


class CohortUpdatedEvent(InngestEventContract):
    """Live cohort summary update."""

    name: ClassVar[str] = "dashboard/cohort.updated"

    cohort_id: UUID
    summary: CohortSummaryDto


# ---------------------------------------------------------------------------
# Graph mutation events (dynamic delegation observability)
# ---------------------------------------------------------------------------


class DashboardGraphMutationEvent(InngestEventContract):
    name: ClassVar[str] = "dashboard/graph.mutation"

    mutation: GraphMutationRecordDto


class DashboardContextEventEvent(InngestEventContract):
    name: ClassVar[str] = "dashboard/context.event"

    id: UUID = Field(
        description="RunContextEvent.id used by the frontend as a stable deduplication key."
    )
    run_id: UUID
    task_execution_id: UUID
    task_id: UUID = Field(
        description=(
            "Graph task id resolved from the task execution by the dashboard emitter at "
            "event emission time."
        )
    )
    worker_binding_key: str
    sequence: int
    event_type: ContextEventType
    payload: ContextPartChunkLog = Field(
        description=(
            "Typed context event payload serialized with model_dump(mode='json') before "
            "being sent through Inngest."
        )
    )
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
