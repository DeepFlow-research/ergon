"""Dashboard event emission module.

This module provides event emission for workflow visualization dashboards.
Events are emitted via Inngest and can be consumed by any dashboard implementation.

Usage:
    from h_arcane.dashboard import dashboard_emitter

    await dashboard_emitter.workflow_started(run_id, experiment_id, ...)
    await dashboard_emitter.task_status_changed(run_id, task_id, ...)
"""

from h_arcane.dashboard.emitter import DashboardEmitter, dashboard_emitter
from h_arcane.dashboard.events import (
    DashboardAgentActionCompletedEvent,
    DashboardAgentActionStartedEvent,
    DashboardResourcePublishedEvent,
    DashboardSandboxClosedEvent,
    DashboardSandboxCommandEvent,
    DashboardSandboxCreatedEvent,
    DashboardTaskStatusChangedEvent,
    DashboardWorkflowCompletedEvent,
    DashboardWorkflowStartedEvent,
)

__all__ = [
    # Emitter
    "DashboardEmitter",
    "dashboard_emitter",
    # Workflow Events
    "DashboardWorkflowStartedEvent",
    "DashboardWorkflowCompletedEvent",
    # Task Events
    "DashboardTaskStatusChangedEvent",
    # Agent Events
    "DashboardAgentActionStartedEvent",
    "DashboardAgentActionCompletedEvent",
    # Resource Events
    "DashboardResourcePublishedEvent",
    # Sandbox Events
    "DashboardSandboxCreatedEvent",
    "DashboardSandboxCommandEvent",
    "DashboardSandboxClosedEvent",
]
