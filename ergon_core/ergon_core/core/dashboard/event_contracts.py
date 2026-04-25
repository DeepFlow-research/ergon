"""Dashboard event contracts for real-time UI updates via Inngest.

Every contract here must match the corresponding Zod schema in
ergon-dashboard/src/generated/events/*.ts — the latter is generated from
these models via scripts/export_contract_schemas.py +
json-schema-to-zod (see package.json ``generate:contracts``).  Any
change here that isn't regenerated will fail the CI drift check.
"""

from datetime import datetime
from typing import Any, ClassVar
from uuid import UUID

from pydantic import BaseModel

from ergon_core.core.persistence.context.event_payloads import (
    ContextEventPayload,
    ContextEventType,
)
from ergon_core.core.persistence.graph.models import GraphTargetType, MutationType
from ergon_core.core.runtime.events.base import InngestEventContract
from ergon_core.core.runtime.services.graph_dto import GraphMutationValue

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
    experiment_id: UUID
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
    old_status: str | None = None
    new_status: str
    triggered_by: str | None = None
    timestamp: datetime
    assigned_worker_id: UUID | None = None
    assigned_worker_name: str | None = None


class DashboardTaskEvaluationUpdatedEvent(InngestEventContract):
    """Embeds the full RunTaskEvaluationDto (camelCase) as `evaluation`.

    TODO(E2b, bug file § D): tighten ``evaluation`` to
    ``RunTaskEvaluationDto``.  Deferred because the current emitter in
    ``evaluate_task_run.py`` hand-rolls the dict and doesn't have
    access to the rich criterion metadata (stage_num, stage_name,
    criterion_num, criterion_description) the dashboard schema
    requires.  Fixing both together is an independent unit of work.
    """

    name: ClassVar[str] = "dashboard/task.evaluation_updated"

    run_id: UUID
    task_id: UUID
    evaluation: dict[str, Any]  # slopcop: ignore[no-typing-any]


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
    """Embeds full RunCommunicationThreadDto + RunCommunicationMessageDto (camelCase).

    TODO(E2b): tighten ``thread`` / ``message`` to
    ``RunCommunicationThreadDto`` / ``RunCommunicationMessageDto``.
    Deferred for the same reason as evaluation above — the emitter
    needs an updated construction path.
    """

    name: ClassVar[str] = "dashboard/thread.message_created"

    run_id: UUID
    thread: dict[str, Any]  # slopcop: ignore[no-typing-any]
    message: dict[str, Any]  # slopcop: ignore[no-typing-any]


# ---------------------------------------------------------------------------
# Cohort events
# ---------------------------------------------------------------------------


class CohortUpdatedEvent(InngestEventContract):
    """TODO(E2b): tighten ``summary`` to ``CohortSummaryDto`` and update
    the emitter accordingly."""

    name: ClassVar[str] = "dashboard/cohort.updated"

    cohort_id: UUID
    summary: dict[str, Any]  # slopcop: ignore[no-typing-any]


# ---------------------------------------------------------------------------
# Graph mutation events (dynamic delegation observability)
# ---------------------------------------------------------------------------


class DashboardGraphMutationEvent(InngestEventContract):
    name: ClassVar[str] = "dashboard/graph.mutation"

    run_id: UUID
    sequence: int
    mutation_type: MutationType
    target_type: GraphTargetType
    target_id: UUID
    actor: str
    new_value: GraphMutationValue
    old_value: GraphMutationValue | None = None
    reason: str | None = None
    timestamp: datetime


class DashboardContextEventEvent(InngestEventContract):
    name: ClassVar[str] = "dashboard/context.event"

    id: UUID  # RunContextEvent.id — dedup key on frontend
    run_id: UUID
    task_execution_id: UUID
    task_node_id: UUID  # resolved from _execution_task_map at emit time
    worker_binding_key: str
    sequence: int
    event_type: ContextEventType
    payload: ContextEventPayload  # serialised via model_dump(mode="json")
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
