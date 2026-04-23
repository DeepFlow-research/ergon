"""Fire-and-forget dashboard event emitter.

Every method builds a typed event contract and sends it through the Inngest
client. Errors are caught and logged so callers are never blocked.
"""

import logging
from typing import Any, cast
from uuid import UUID

import inngest
from ergon_core.core.persistence.context.event_payloads import ContextEventType
from ergon_core.core.persistence.context.models import RunContextEvent as _RunContextEvent
from ergon_core.core.persistence.graph.models import (
    GraphTargetType,
    MutationType,
    RunGraphMutation,
)
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.telemetry.models import RunRecord
from ergon_core.core.runtime.events.task_events import TaskCancelledEvent
from ergon_core.core.runtime.inngest_client import inngest_client
from ergon_core.core.runtime.services.cohort_service import experiment_cohort_service
from ergon_core.core.runtime.services.cohort_stats_service import (
    experiment_cohort_stats_service,
)
from ergon_core.core.runtime.services.graph_dto import GraphMutationValue
from ergon_core.core.utils import utcnow
from pydantic import TypeAdapter

from ergon_core.core.dashboard.event_contracts import (
    CohortUpdatedEvent,
    DashboardContextEventEvent,
    DashboardGraphMutationEvent,
    DashboardResourcePublishedEvent,
    DashboardSandboxClosedEvent,
    DashboardSandboxCommandEvent,
    DashboardSandboxCreatedEvent,
    DashboardTaskEvaluationUpdatedEvent,
    DashboardTaskStatusChangedEvent,
    DashboardThreadMessageCreatedEvent,
    DashboardWorkflowCompletedEvent,
    TaskTreeNode,
    DashboardWorkflowStartedEvent,
)

_MUTATION_VALUE_ADAPTER: TypeAdapter[GraphMutationValue] = TypeAdapter(GraphMutationValue)

logger = logging.getLogger(__name__)


class DashboardEmitter:
    """Sends dashboard events via Inngest for real-time UI updates."""

    def __init__(self, *, enabled: bool = True) -> None:
        self._enabled = enabled
        self._execution_task_map: dict[UUID, UUID] = {}

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value

    # ------------------------------------------------------------------
    # Workflow
    # ------------------------------------------------------------------

    async def workflow_started(
        self,
        run_id: UUID,
        experiment_id: UUID,
        workflow_name: str,
        task_tree: TaskTreeNode,
        total_tasks: int,
        total_leaf_tasks: int,
    ) -> None:
        if not self._enabled:
            return
        try:
            evt = DashboardWorkflowStartedEvent(
                run_id=run_id,
                experiment_id=experiment_id,
                workflow_name=workflow_name,
                task_tree=task_tree,
                started_at=utcnow(),
                total_tasks=total_tasks,
                total_leaf_tasks=total_leaf_tasks,
            )
            await inngest_client.send(
                inngest.Event(name=evt.name, data=evt.model_dump(mode="json"))
            )
        except Exception:  # slopcop: ignore[no-broad-except]
            logger.warning("Failed to emit dashboard/workflow.started", exc_info=True)

    async def workflow_completed(
        self,
        run_id: UUID,
        status: str,
        duration_seconds: float,
        final_score: float | None = None,
        error: str | None = None,
    ) -> None:
        if not self._enabled:
            return
        try:
            evt = DashboardWorkflowCompletedEvent(
                run_id=run_id,
                status=status,
                completed_at=utcnow(),
                duration_seconds=duration_seconds,
                final_score=final_score,
                error=error,
            )
            await inngest_client.send(
                inngest.Event(name=evt.name, data=evt.model_dump(mode="json"))
            )
        except Exception:  # slopcop: ignore[no-broad-except]
            logger.warning("Failed to emit dashboard/workflow.completed", exc_info=True)

    # ------------------------------------------------------------------
    # Task
    # ------------------------------------------------------------------

    async def task_status_changed(  # slopcop: ignore[max-function-params]
        self,
        run_id: UUID,
        task_id: UUID,
        task_name: str,
        new_status: str,
        old_status: str | None = None,
        parent_task_id: UUID | None = None,
        triggered_by: str | None = None,
        assigned_worker_id: UUID | None = None,
        assigned_worker_name: str | None = None,
    ) -> None:
        if not self._enabled:
            return
        try:
            evt = DashboardTaskStatusChangedEvent(
                run_id=run_id,
                task_id=task_id,
                task_name=task_name,
                parent_task_id=parent_task_id,
                old_status=old_status,
                new_status=new_status,
                triggered_by=triggered_by,
                timestamp=utcnow(),
                assigned_worker_id=assigned_worker_id,
                assigned_worker_name=assigned_worker_name,
            )
            await inngest_client.send(
                inngest.Event(name=evt.name, data=evt.model_dump(mode="json"))
            )
        except Exception:  # slopcop: ignore[no-broad-except]
            logger.warning("Failed to emit dashboard/task.status_changed", exc_info=True)

    async def task_evaluation_updated(
        self,
        run_id: UUID,
        task_id: UUID,
        evaluation: dict[str, Any],  # slopcop: ignore[no-typing-any]
    ) -> None:
        """Send evaluation update. `evaluation` must be a camelCase RunTaskEvaluationDto dict."""
        if not self._enabled:
            return
        try:
            evt = DashboardTaskEvaluationUpdatedEvent(
                run_id=run_id,
                task_id=task_id,
                evaluation=evaluation,
            )
            await inngest_client.send(
                inngest.Event(name=evt.name, data=evt.model_dump(mode="json"))
            )
        except Exception:  # slopcop: ignore[no-broad-except]
            logger.warning("Failed to emit dashboard/task.evaluation_updated", exc_info=True)

    async def task_cancelled(self, event: TaskCancelledEvent) -> None:
        """Emit a task status change to 'cancelled' for the dashboard.

        Called when a ``TaskCancelledEvent`` is processed so the real-time
        dashboard can reflect the cancellation immediately.
        """
        if not self._enabled:
            return
        try:
            evt = DashboardTaskStatusChangedEvent(
                run_id=event.run_id,
                task_id=event.node_id,
                task_name="",
                parent_task_id=None,
                old_status=None,
                new_status="cancelled",
                triggered_by=f"cancel:{event.cause}",
                timestamp=utcnow(),
                assigned_worker_id=None,
                assigned_worker_name=None,
            )
            await inngest_client.send(
                inngest.Event(name=evt.name, data=evt.model_dump(mode="json"))
            )
        except Exception:  # slopcop: ignore[no-broad-except]
            logger.warning("Failed to emit dashboard/task.cancelled", exc_info=True)

    # ------------------------------------------------------------------
    # Resources
    # ------------------------------------------------------------------

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
        if not self._enabled:
            return
        try:
            evt = DashboardResourcePublishedEvent(
                run_id=run_id,
                task_id=task_id,
                task_execution_id=task_execution_id,
                resource_id=resource_id,
                resource_name=resource_name,
                mime_type=mime_type,
                size_bytes=size_bytes,
                file_path=file_path,
                timestamp=utcnow(),
            )
            await inngest_client.send(
                inngest.Event(name=evt.name, data=evt.model_dump(mode="json"))
            )
        except Exception:  # slopcop: ignore[no-broad-except]
            logger.warning("Failed to emit dashboard/resource.published", exc_info=True)

    # ------------------------------------------------------------------
    # Sandbox
    # ------------------------------------------------------------------

    async def sandbox_created(
        self,
        run_id: UUID,
        task_id: UUID,
        sandbox_id: str,
        timeout_minutes: int,
        template: str | None = None,
    ) -> None:
        if not self._enabled:
            return
        try:
            evt = DashboardSandboxCreatedEvent(
                run_id=run_id,
                task_id=task_id,
                sandbox_id=sandbox_id,
                template=template,
                timeout_minutes=timeout_minutes,
                timestamp=utcnow(),
            )
            await inngest_client.send(
                inngest.Event(name=evt.name, data=evt.model_dump(mode="json"))
            )
        except Exception:  # slopcop: ignore[no-broad-except]
            logger.warning("Failed to emit dashboard/sandbox.created", exc_info=True)

    async def sandbox_command(
        self,
        run_id: UUID,
        task_id: UUID,
        sandbox_id: str,
        command: str,
        stdout: str | None = None,
        stderr: str | None = None,
        exit_code: int | None = None,
        duration_ms: int | None = None,
    ) -> None:
        if not self._enabled:
            return
        try:
            evt = DashboardSandboxCommandEvent(
                run_id=run_id,
                task_id=task_id,
                sandbox_id=sandbox_id,
                command=command,
                stdout=stdout,
                stderr=stderr,
                exit_code=exit_code,
                duration_ms=duration_ms,
                timestamp=utcnow(),
            )
            await inngest_client.send(
                inngest.Event(name=evt.name, data=evt.model_dump(mode="json"))
            )
        except Exception:  # slopcop: ignore[no-broad-except]
            logger.warning("Failed to emit dashboard/sandbox.command", exc_info=True)

    async def sandbox_closed(
        self,
        task_id: UUID,
        sandbox_id: str,
        reason: str,
    ) -> None:
        if not self._enabled:
            return
        try:
            evt = DashboardSandboxClosedEvent(
                task_id=task_id,
                sandbox_id=sandbox_id,
                reason=reason,
                timestamp=utcnow(),
            )
            await inngest_client.send(
                inngest.Event(name=evt.name, data=evt.model_dump(mode="json"))
            )
        except Exception:  # slopcop: ignore[no-broad-except]
            logger.warning("Failed to emit dashboard/sandbox.closed", exc_info=True)

    # ------------------------------------------------------------------
    # Thread / messaging
    # ------------------------------------------------------------------

    async def thread_message_created(
        self,
        run_id: UUID,
        thread: dict[str, Any],  # slopcop: ignore[no-typing-any]
        message: dict[str, Any],  # slopcop: ignore[no-typing-any]
    ) -> None:
        """Send thread message event. `thread` and `message` must be camelCase DTO dicts."""
        if not self._enabled:
            return
        try:
            evt = DashboardThreadMessageCreatedEvent(
                run_id=run_id,
                thread=thread,
                message=message,
            )
            await inngest_client.send(
                inngest.Event(name=evt.name, data=evt.model_dump(mode="json"))
            )
        except Exception:  # slopcop: ignore[no-broad-except]
            logger.warning("Failed to emit dashboard/thread.message_created", exc_info=True)

    # ------------------------------------------------------------------
    # Graph mutations (repository listener)
    # ------------------------------------------------------------------

    async def graph_mutation(self, row: RunGraphMutation) -> None:
        """Called by WorkflowGraphRepository after a mutation is flushed to PG."""
        if not self._enabled:
            return
        try:
            raw_new = {"mutation_type": row.mutation_type, **row.new_value}
            new_value = _MUTATION_VALUE_ADAPTER.validate_python(raw_new)

            old_value: GraphMutationValue | None = None
            if row.old_value:
                raw_old = {"mutation_type": row.mutation_type, **row.old_value}
                old_value = _MUTATION_VALUE_ADAPTER.validate_python(raw_old)

            evt = DashboardGraphMutationEvent(
                run_id=row.run_id,
                sequence=row.sequence,
                mutation_type=cast(MutationType, row.mutation_type),
                target_type=cast(GraphTargetType, row.target_type),
                target_id=row.target_id,
                actor=row.actor,
                new_value=new_value,
                old_value=old_value,
                reason=row.reason,
                timestamp=row.created_at,
            )
            await inngest_client.send(
                inngest.Event(name=evt.name, data=evt.model_dump(mode="json"))
            )
        except Exception:  # slopcop: ignore[no-broad-except]
            logger.warning("Failed to emit dashboard/graph.mutation", exc_info=True)

    # ------------------------------------------------------------------
    # Context events (repository listener)
    # ------------------------------------------------------------------

    def register_execution(self, execution_id: UUID, task_node_id: UUID) -> None:
        """Register execution_id → task graph node_id mapping.
        Called from worker_execute.py before persist_turn so that on_context_event
        can resolve task_node_id without a DB lookup."""
        self._execution_task_map[execution_id] = task_node_id

    async def on_context_event(self, event: "_RunContextEvent") -> None:
        """Called by ContextEventRepository after each event is committed."""
        if not self._enabled:
            return
        try:
            # reason: avoid circular import at module level between dashboard and persistence layers
            from ergon_core.core.persistence.context.models import _PAYLOAD_ADAPTER  # noqa: PLC2701

            task_node_id = self._execution_task_map.get(event.task_execution_id)
            if task_node_id is None:
                logger.warning(
                    "on_context_event: no task_node_id for execution %s",
                    event.task_execution_id,
                )
                return
            evt = DashboardContextEventEvent(
                id=event.id,
                run_id=event.run_id,
                task_execution_id=event.task_execution_id,
                task_node_id=task_node_id,
                worker_binding_key=event.worker_binding_key,
                sequence=event.sequence,
                event_type=cast(ContextEventType, event.event_type),
                payload=_PAYLOAD_ADAPTER.validate_python(event.payload),
                created_at=event.created_at,
                started_at=event.started_at,
                completed_at=event.completed_at,
            )
            await inngest_client.send(
                inngest.Event(name=evt.name, data=evt.model_dump(mode="json"))
            )
        except Exception:  # slopcop: ignore[no-broad-except]
            logger.warning("Failed to emit dashboard/context.event", exc_info=True)

    # ------------------------------------------------------------------
    # Cohort
    # ------------------------------------------------------------------

    async def cohort_updated(
        self,
        cohort_id: UUID,
        summary: dict[str, Any],  # slopcop: ignore[no-typing-any]
    ) -> None:
        """Send cohort update. `summary` must be a camelCase CohortSummaryDto dict."""
        if not self._enabled:
            return
        try:
            evt = CohortUpdatedEvent(
                cohort_id=cohort_id,
                summary=summary,
            )
            await inngest_client.send(
                inngest.Event(name=evt.name, data=evt.model_dump(mode="json"))
            )
        except Exception:  # slopcop: ignore[no-broad-except]
            logger.warning("Failed to emit dashboard/cohort.updated", exc_info=True)


dashboard_emitter = DashboardEmitter(enabled=True)


async def emit_cohort_updated_for_run(run_id: UUID) -> None:
    """Refresh and emit the current cohort summary for a run, if it has a cohort."""
    with get_session() as session:
        run = session.get(RunRecord, run_id)
        if run is None or run.cohort_id is None:
            return

        cohort_id = run.cohort_id

    experiment_cohort_stats_service.recompute(cohort_id)
    summary = experiment_cohort_service.get_summary(cohort_id)
    if summary is None:
        return
    await dashboard_emitter.cohort_updated(
        cohort_id=summary.cohort_id,
        summary=summary.model_dump(mode="json"),
    )
