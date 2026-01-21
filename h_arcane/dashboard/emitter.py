"""Dashboard event emitter.

Wraps Inngest event sending with dashboard-specific payloads.
Uses the existing InngestEventContract classes from events.py.

The emitter provides a clean API for emitting dashboard events from
the orchestration layer (Inngest functions). All events use the
"dashboard/" prefix to avoid interference with orchestration events.

Usage:
    from h_arcane.dashboard import dashboard_emitter

    # In an Inngest function:
    await dashboard_emitter.workflow_started(
        run_id=run_id,  # UUID - no str() conversion needed
        experiment_id=experiment_id,
        workflow_name="My Workflow",
        task_tree=tree.model_dump(),
        total_tasks=10,
        total_leaf_tasks=5,
    )
"""

from datetime import datetime, timezone
from logging import getLogger
from uuid import UUID

import inngest

from h_arcane.core._internal.infrastructure.inngest_client import inngest_client
from h_arcane.core._internal.task.schema import TaskTreeNode
from h_arcane.core.status import TaskStatus, TaskTrigger
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

logger = getLogger(__name__)


class DashboardEmitter:
    """
    Emits events for dashboard consumption.

    Uses the InngestEventContract pattern from h_arcane.dashboard.events.
    Events are sent asynchronously via Inngest and do not block the main
    execution flow.

    The emitter can be disabled via the `enabled` flag for testing or
    when dashboard visualization is not needed.

    Attributes:
        enabled: Whether to emit events (default: True)
    """

    def __init__(self, enabled: bool = True):
        """Initialize the emitter.

        Args:
            enabled: Whether to emit events. Set to False to disable
                     all event emission (useful for testing).
        """
        self._enabled = enabled

    @property
    def enabled(self) -> bool:
        """Whether the emitter is enabled."""
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        """Enable or disable the emitter."""
        self._enabled = value

    def _now(self) -> datetime:
        """Get current UTC time."""
        return datetime.now(timezone.utc)

    async def workflow_started(
        self,
        run_id: UUID,
        experiment_id: UUID,
        workflow_name: str,
        task_tree: TaskTreeNode,
        total_tasks: int,
        total_leaf_tasks: int,
    ) -> None:
        """Emit workflow started event.

        Called when execute_task() begins a new workflow execution.
        """
        if not self._enabled:
            return

        event = DashboardWorkflowStartedEvent(
            run_id=run_id,
            experiment_id=experiment_id,
            workflow_name=workflow_name,
            task_tree=task_tree,
            started_at=self._now(),
            total_tasks=total_tasks,
            total_leaf_tasks=total_leaf_tasks,
        )
        try:
            await inngest_client.send(
                inngest.Event(name=event.name, data=event.model_dump(mode="json"))
            )
        except Exception as e:
            logger.warning(f"Failed to emit {event.name}: {e}")

    async def workflow_completed(
        self,
        run_id: UUID,
        status: str,
        duration_seconds: float,
        final_score: float | None = None,
        error: str | None = None,
    ) -> None:
        """Emit workflow completed event.

        Called when a workflow finishes (success or failure).
        """
        if not self._enabled:
            return

        event = DashboardWorkflowCompletedEvent(
            run_id=run_id,
            status=status,
            completed_at=self._now(),
            duration_seconds=duration_seconds,
            final_score=final_score,
            error=error,
        )
        try:
            await inngest_client.send(
                inngest.Event(name=event.name, data=event.model_dump(mode="json"))
            )
        except Exception as e:
            logger.warning(f"Failed to emit {event.name}: {e}")

    async def task_status_changed(
        self,
        run_id: UUID,
        task_id: UUID,
        task_name: str,
        new_status: TaskStatus,
        parent_task_id: str | None = None,
        old_status: TaskStatus | None = None,
        triggered_by: TaskTrigger | None = None,
        assigned_worker_id: UUID | None = None,
        assigned_worker_name: str | None = None,
    ) -> None:
        """Emit task status changed event.

        Called on any task status transition (pending -> ready -> running -> completed/failed).
        """
        if not self._enabled:
            return

        event = DashboardTaskStatusChangedEvent(
            run_id=run_id,
            task_id=task_id,
            task_name=task_name,
            parent_task_id=parent_task_id,
            old_status=old_status,
            new_status=new_status,
            triggered_by=triggered_by,
            timestamp=self._now(),
            assigned_worker_id=assigned_worker_id,
            assigned_worker_name=assigned_worker_name,
        )
        try:
            await inngest_client.send(
                inngest.Event(name=event.name, data=event.model_dump(mode="json"))
            )
        except Exception as e:
            logger.warning(f"Failed to emit {event.name}: {e}")

    async def agent_action_started(
        self,
        run_id: UUID,
        task_id: UUID,
        action_id: UUID,
        worker_id: UUID,
        worker_name: str,
        action_type: str,
        action_input: str,
    ) -> None:
        """Emit agent action started event.

        Called when an agent begins a tool call.
        """
        if not self._enabled:
            return

        event = DashboardAgentActionStartedEvent(
            run_id=run_id,
            task_id=task_id,
            action_id=action_id,
            worker_id=worker_id,
            worker_name=worker_name,
            action_type=action_type,
            action_input=action_input,
            timestamp=self._now(),
        )
        try:
            await inngest_client.send(
                inngest.Event(name=event.name, data=event.model_dump(mode="json"))
            )
        except Exception as e:
            logger.warning(f"Failed to emit {event.name}: {e}")

    async def agent_action_completed(
        self,
        run_id: UUID,
        task_id: UUID,
        action_id: UUID,
        worker_id: UUID,
        action_type: str,
        duration_ms: int,
        success: bool,
        action_output: str | None = None,
        error: str | None = None,
    ) -> None:
        """Emit agent action completed event.

        Called when an agent completes a tool call.
        """
        if not self._enabled:
            return

        event = DashboardAgentActionCompletedEvent(
            run_id=run_id,
            task_id=task_id,
            action_id=action_id,
            worker_id=worker_id,
            action_type=action_type,
            action_output=action_output,
            duration_ms=duration_ms,
            success=success,
            error=error,
            timestamp=self._now(),
        )
        try:
            await inngest_client.send(
                inngest.Event(name=event.name, data=event.model_dump(mode="json"))
            )
        except Exception as e:
            logger.warning(f"Failed to emit {event.name}: {e}")

    async def resource_published(
        self,
        run_id: UUID,
        task_id: UUID,
        task_execution_id: UUID,
        resource_id: UUID,
        resource_name: str,
        mime_type: str,
        size_bytes: int,
        file_path: str,
    ) -> None:
        """Emit resource published event.

        Called when a task produces an output resource (file).
        """
        if not self._enabled:
            return

        event = DashboardResourcePublishedEvent(
            run_id=run_id,
            task_id=task_id,
            task_execution_id=task_execution_id,
            resource_id=resource_id,
            resource_name=resource_name,
            mime_type=mime_type,
            size_bytes=size_bytes,
            file_path=file_path,
            timestamp=self._now(),
        )
        try:
            await inngest_client.send(
                inngest.Event(name=event.name, data=event.model_dump(mode="json"))
            )
        except Exception as e:
            logger.warning(f"Failed to emit {event.name}: {e}")

    async def sandbox_created(
        self,
        task_id: UUID,
        sandbox_id: str,
        timeout_minutes: int,
        template: str | None = None,
    ) -> None:
        """Emit sandbox created event.

        Called when an E2B sandbox is created for a task.
        """
        if not self._enabled:
            return

        event = DashboardSandboxCreatedEvent(
            task_id=task_id,
            sandbox_id=sandbox_id,
            template=template,
            timeout_minutes=timeout_minutes,
            timestamp=self._now(),
        )
        try:
            await inngest_client.send(
                inngest.Event(name=event.name, data=event.model_dump(mode="json"))
            )
        except Exception as e:
            logger.warning(f"Failed to emit {event.name}: {e}")

    async def sandbox_command(
        self,
        task_id: UUID,
        sandbox_id: str,
        command: str,
        stdout: str | None = None,
        stderr: str | None = None,
        exit_code: int | None = None,
        duration_ms: int | None = None,
    ) -> None:
        """Emit sandbox command event.

        Called when a command is executed in a sandbox.
        """
        if not self._enabled:
            return

        event = DashboardSandboxCommandEvent(
            task_id=task_id,
            sandbox_id=sandbox_id,
            command=command,
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            duration_ms=duration_ms,
            timestamp=self._now(),
        )
        try:
            await inngest_client.send(
                inngest.Event(name=event.name, data=event.model_dump(mode="json"))
            )
        except Exception as e:
            logger.warning(f"Failed to emit {event.name}: {e}")

    async def sandbox_closed(
        self,
        task_id: UUID,
        sandbox_id: str,
        reason: str,
    ) -> None:
        """Emit sandbox closed event.

        Called when a sandbox is terminated.
        """
        if not self._enabled:
            return

        event = DashboardSandboxClosedEvent(
            task_id=task_id,
            sandbox_id=sandbox_id,
            reason=reason,
            timestamp=self._now(),
        )
        try:
            await inngest_client.send(
                inngest.Event(name=event.name, data=event.model_dump(mode="json"))
            )
        except Exception as e:
            logger.warning(f"Failed to emit {event.name}: {e}")


# Global instance (can be disabled via config or for testing)
dashboard_emitter = DashboardEmitter(enabled=True)
