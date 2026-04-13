"""Fire-and-forget dashboard event emitter.

Every method builds a typed event contract and sends it through the Inngest
client. Errors are caught and logged so callers are never blocked.
"""

import logging
from typing import Any
from uuid import UUID

import inngest
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.telemetry.models import RunRecord
from ergon_core.core.runtime.inngest_client import inngest_client
from ergon_core.core.runtime.services.cohort_service import experiment_cohort_service
from ergon_core.core.runtime.services.cohort_stats_service import (
    experiment_cohort_stats_service,
)
from ergon_core.core.utils import utcnow

from ergon_core.core.persistence.telemetry.models import RunGenerationTurn

from .event_contracts import (
    CohortUpdatedEvent,
    DashboardAgentActionCompletedEvent,
    DashboardAgentActionStartedEvent,
    DashboardGenerationTurnEvent,
    DashboardResourcePublishedEvent,
    DashboardSandboxClosedEvent,
    DashboardSandboxCommandEvent,
    DashboardSandboxCreatedEvent,
    DashboardTaskEvaluationUpdatedEvent,
    DashboardTaskStatusChangedEvent,
    DashboardThreadMessageCreatedEvent,
    DashboardWorkflowCompletedEvent,
    DashboardWorkflowStartedEvent,
)

logger = logging.getLogger(__name__)


class DashboardEmitter:
    """Sends dashboard events via Inngest for real-time UI updates."""

    def __init__(self, *, enabled: bool = True) -> None:
        self._enabled = enabled

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
        task_tree: dict[str, Any],  # slopcop: ignore[no-typing-any]
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

    # ------------------------------------------------------------------
    # Agent actions
    # ------------------------------------------------------------------

    async def agent_action_started(
        self,
        run_id: UUID,
        task_id: UUID,
        action_id: str,
        worker_id: UUID,
        worker_name: str,
        action_type: str,
        action_input: str,
    ) -> None:
        if not self._enabled:
            return
        try:
            evt = DashboardAgentActionStartedEvent(
                run_id=run_id,
                task_id=task_id,
                action_id=action_id,
                worker_id=worker_id,
                worker_name=worker_name,
                action_type=action_type,
                action_input=action_input,
                timestamp=utcnow(),
            )
            await inngest_client.send(
                inngest.Event(name=evt.name, data=evt.model_dump(mode="json"))
            )
        except Exception:  # slopcop: ignore[no-broad-except]
            logger.warning("Failed to emit dashboard/agent.action_started", exc_info=True)

    async def agent_action_completed(  # slopcop: ignore[max-function-params]
        self,
        run_id: UUID,
        task_id: UUID,
        action_id: str,
        worker_id: UUID,
        action_type: str,
        duration_ms: int,
        success: bool = True,
        action_output: str | None = None,
        error: str | None = None,
    ) -> None:
        if not self._enabled:
            return
        try:
            evt = DashboardAgentActionCompletedEvent(
                run_id=run_id,
                task_id=task_id,
                action_id=action_id,
                worker_id=worker_id,
                action_type=action_type,
                action_output=action_output,
                duration_ms=duration_ms,
                success=success,
                error=error,
                timestamp=utcnow(),
            )
            await inngest_client.send(
                inngest.Event(name=evt.name, data=evt.model_dump(mode="json"))
            )
        except Exception:  # slopcop: ignore[no-broad-except]
            logger.warning("Failed to emit dashboard/agent.action_completed", exc_info=True)

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
    # Generation turns (repository listener)
    # ------------------------------------------------------------------

    async def on_turn_persisted(self, row: RunGenerationTurn) -> None:
        """Called by GenerationTurnRepository after a turn is committed to PG."""
        if not self._enabled:
            return
        try:
            evt = DashboardGenerationTurnEvent(
                run_id=row.run_id,
                task_execution_id=row.task_execution_id,
                worker_binding_key=row.worker_binding_key,
                worker_name=row.worker_binding_key,
                turn_index=row.turn_index,
                response_text=row.response_text,
                tool_calls=row.tool_calls_json,
                policy_version=row.policy_version,
            )
            await inngest_client.send(
                inngest.Event(name=evt.name, data=evt.model_dump(mode="json"))
            )
        except Exception:  # slopcop: ignore[no-broad-except]
            logger.warning("Failed to emit dashboard/generation.turn_completed", exc_info=True)

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
