"""Dashboard emission module — re-exports for convenience."""

from ergon_core.core.infrastructure.dashboard.emitter import (
    DashboardEmitter,
    emit_cohort_updated_for_run,
)
from ergon_core.core.infrastructure.dashboard.event_contracts import (
    CohortUpdatedEvent,
    DashboardResourcePublishedEvent,
    DashboardSandboxClosedEvent,
    DashboardSandboxCommandEvent,
    DashboardSandboxCreatedEvent,
    DashboardTaskEvaluationUpdatedEvent,
    DashboardTaskStatusChangedEvent,
    DashboardThreadMessageCreatedEvent,
    DashboardWorkflowCompletedEvent,
    DashboardWorkflowStartedEvent,
    TaskTreeNode,
)
from ergon_core.core.infrastructure.dashboard.provider import (
    get_dashboard_emitter,
    init_dashboard_emitter,
    reset_dashboard_emitter,
    set_dashboard_emitter,
)

__all__ = [
    "CohortUpdatedEvent",
    "DashboardEmitter",
    "DashboardResourcePublishedEvent",
    "DashboardSandboxClosedEvent",
    "DashboardSandboxCommandEvent",
    "DashboardSandboxCreatedEvent",
    "DashboardTaskEvaluationUpdatedEvent",
    "DashboardTaskStatusChangedEvent",
    "DashboardThreadMessageCreatedEvent",
    "DashboardWorkflowCompletedEvent",
    "DashboardWorkflowStartedEvent",
    "TaskTreeNode",
    "emit_cohort_updated_for_run",
    "get_dashboard_emitter",
    "init_dashboard_emitter",
    "reset_dashboard_emitter",
    "set_dashboard_emitter",
]
