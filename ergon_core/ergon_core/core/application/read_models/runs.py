"""Read service for dashboard/API run snapshots and related views."""

import os
from pathlib import Path
from uuid import UUID

from ergon_core.core.application.read_models.models import (
    RunSnapshotDto,
)
from ergon_core.core.persistence.context.models import RunContextEvent
from ergon_core.core.persistence.definitions.models import (
    ExperimentDefinition,
    ExperimentDefinitionWorker,
)
from ergon_core.core.persistence.graph.models import RunGraphEdge, RunGraphMutation, RunGraphNode
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.shared.enums import RunStatus
from ergon_core.core.persistence.telemetry.models import (
    RunRecord,
    RunResource,
    RunTaskEvaluation,
    RunTaskExecution,
    Thread,
    ThreadMessage,
)
from ergon_core.core.application.graph.models import GraphMutationRecordDto
from ergon_core.core.application.evaluation.scoring import (
    EvaluationScoreSummary,
    aggregate_evaluation_scores,
)
from ergon_core.core.application.read_models.run_snapshot import (
    _build_communication_threads,
    _build_task_map,
    _context_events_by_task,
    _task_keyed_evaluations,
    _task_keyed_executions,
    _task_keyed_resources,
    _task_keyed_sandboxes,
    _task_timestamps,
)
from ergon_core.core.application.read_models.resources import require_viewable_resource_size
from pydantic import BaseModel
from sqlmodel import select


class RunResourceBlob(BaseModel):
    model_config = {"frozen": True}

    path: Path
    media_type: str
    filename: str


class RunReadService:
    """Owns database reads and DTO shaping for run API endpoints."""

    def build_run_snapshot(self, run_id: UUID) -> RunSnapshotDto | None:
        with get_session() as session:
            run = session.get(RunRecord, run_id)
            if run is None:
                return None

            definition = session.get(ExperimentDefinition, run.definition_id)
            if definition is None:
                return None

            def_id = run.definition_id
            nodes = list(
                session.exec(select(RunGraphNode).where(RunGraphNode.run_id == run_id)).all()
            )
            edges = list(
                session.exec(select(RunGraphEdge).where(RunGraphEdge.run_id == run_id)).all()
            )
            def_workers = list(
                session.exec(
                    select(ExperimentDefinitionWorker).where(
                        ExperimentDefinitionWorker.experiment_definition_id == def_id
                    )
                ).all()
            )
            executions = list(
                session.exec(
                    select(RunTaskExecution).where(RunTaskExecution.run_id == run_id)
                ).all()
            )
            resources = list(
                session.exec(select(RunResource).where(RunResource.run_id == run_id)).all()
            )
            evaluations = list(
                session.exec(
                    select(RunTaskEvaluation).where(RunTaskEvaluation.run_id == run_id)
                ).all()
            )
            threads = list(session.exec(select(Thread).where(Thread.run_id == run_id)).all())
            thread_messages = list(
                session.exec(select(ThreadMessage).where(ThreadMessage.run_id == run_id)).all()
            )
            context_events = list(
                session.exec(
                    select(RunContextEvent)
                    .where(RunContextEvent.run_id == run_id)
                    .order_by(RunContextEvent.task_execution_id, RunContextEvent.sequence)
                ).all()
            )

        worker_by_id: dict[UUID, ExperimentDefinitionWorker] = {w.id: w for w in def_workers}
        worker_by_binding: dict[str, ExperimentDefinitionWorker] = {
            w.binding_key: w for w in def_workers
        }
        timestamps = _task_timestamps(executions)
        (
            task_map,
            root_task_id,
            total_tasks,
            total_leaf,
            completed_tasks,
            failed_tasks,
            running_tasks,
            cancelled_tasks,
        ) = _build_task_map(nodes, edges, worker_by_binding, timestamps)

        execution_task_map: dict[UUID, UUID] = {ex.id: ex.task_id for ex in executions}

        context_events_by_task = _context_events_by_task(
            context_events,
            execution_task_map,
        )

        score_summary = aggregate_evaluation_scores(evaluations)

        duration_seconds: float | None = None
        if run.started_at and run.completed_at:
            duration_seconds = (run.completed_at - run.started_at).total_seconds()

        run_id_str = str(run.id)
        run_summary = run.parsed_summary()
        meta = definition.parsed_metadata()
        run_name = str(meta.get("name", definition.benchmark_type))

        return RunSnapshotDto(
            id=run_id_str,
            definition_id=str(run.definition_id),
            name=run_name,
            status=run.status,
            tasks=task_map,
            root_task_id=root_task_id,
            resources_by_task=_task_keyed_resources(
                resources,
                execution_task_map,
            ),
            executions_by_task=_task_keyed_executions(
                executions,
                worker_by_id,
            ),
            evaluations_by_task=_task_keyed_evaluations(
                evaluations,
                run_id_str,
            ),
            context_events_by_task=dict(context_events_by_task),
            sandboxes_by_task=_task_keyed_sandboxes(run_summary),
            threads=_build_communication_threads(
                threads,
                thread_messages,
                execution_task_map,
            ),
            started_at=run.started_at or run.created_at,
            completed_at=run.completed_at,
            duration_seconds=duration_seconds,
            total_tasks=total_tasks,
            total_leaf_tasks=total_leaf,
            completed_tasks=completed_tasks,
            failed_tasks=failed_tasks,
            running_tasks=running_tasks,
            cancelled_tasks=cancelled_tasks,
            final_score=_display_run_score(score_summary, run.status),
            error=run.error_message,
        )

    def list_mutations(self, run_id: UUID) -> list[GraphMutationRecordDto] | None:
        with get_session() as session:
            run = session.get(RunRecord, run_id)
            if run is None:
                return None
            mutations = list(
                session.exec(
                    select(RunGraphMutation)
                    .where(RunGraphMutation.run_id == run_id)
                    .order_by(RunGraphMutation.sequence)
                ).all()
            )

        return [
            GraphMutationRecordDto(
                id=m.id,
                run_id=m.run_id,
                sequence=m.sequence,
                mutation_type=m.mutation_type,
                target_type=m.target_type,
                target_id=m.target_id,
                actor=m.actor,
                old_value=m.old_value,
                new_value=m.new_value,
                reason=m.reason,
                created_at=m.created_at,
            )
            for m in mutations
        ]

    def get_resource_blob(self, run_id: UUID, resource_id: UUID) -> RunResourceBlob | None:
        with get_session() as session:
            resource = session.exec(
                select(RunResource).where(
                    RunResource.id == resource_id,
                    RunResource.run_id == run_id,
                )
            ).first()

        if resource is None or resource.file_path is None:
            return None

        blob_path = Path(resource.file_path).resolve(strict=True)
        blob_path.relative_to(_blob_root())
        size = blob_path.stat().st_size
        require_viewable_resource_size(size)
        return RunResourceBlob(
            path=blob_path,
            media_type=resource.mime_type or "application/octet-stream",
            filename=resource.name,
        )


def _display_run_score(score_summary: EvaluationScoreSummary, run_status: str) -> float | None:
    if run_status != RunStatus.COMPLETED:
        return None
    # TODO: this is a hack, we need to fix the calculation / rename variables to make clear that the output score should be normalised by here.
    return score_summary.normalized_score


def _blob_root() -> Path:
    return (
        Path(os.environ.get("ERGON_BLOB_ROOT", "/var/ergon/blob")).resolve()
    )  # TODO: this should be set in pydantic-settings, not with this os fallback we dont ever set
