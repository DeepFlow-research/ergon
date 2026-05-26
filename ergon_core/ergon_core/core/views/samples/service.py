"""Read service for dashboard/API run snapshots and related views."""

import os
from contextlib import AbstractContextManager
from pathlib import Path
from datetime import datetime
from uuid import UUID

from ergon_core.core.views.samples.models import (
    SampleDetailView,
    SampleEventView,
    SampleEventsView,
    SampleGraphEdgeView,
    SampleGraphNodeView,
    SampleGraphView,
    SampleStateView,
    SampleSnapshotMetricsDto,
    SampleSummaryDto,
    SampleSnapshotDto,
)
from ergon_core.core.persistence.context.models import SampleContextEvent
from ergon_core.core.persistence.definitions.models import (
    ExperimentDefinition,
    ExperimentDefinitionWorker,
)
from ergon_core.core.persistence.experiments.models import ExperimentEnvironmentRow
from ergon_core.core.persistence.graph.models import (
    SampleGraphEdge,
    SampleGraphNode,
)
from ergon_core.core.application.samples.events import (
    SampleRuntimeEventReadService,
    SampleRuntimeEventView,
)
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.shared.enums import SampleStatus
from ergon_core.core.persistence.telemetry.models import (
    SampleRecord,
    SampleResource,
    SampleTaskEvaluation,
    SampleTaskAttempt,
    Thread,
    ThreadMessage,
)
from ergon_core.core.application.evaluation.service import (
    EvaluationScoreSummary,
    EvaluationService,
)
from ergon_core.core.views.samples.snapshot import (
    _build_communication_threads,
    _build_task_map,
    _context_events_by_task,
    _task_keyed_evaluations,
    _task_keyed_executions,
    _task_keyed_resources,
    _task_keyed_sandboxes,
    _task_timestamps,
)
from ergon_core.core.views.resources import require_viewable_resource_size
from ergon_core.core.views.samples.metrics import aggregate_run_metrics, observed_cost_from_summary
from pydantic import BaseModel
from sqlmodel import Session, col, select


class SampleResourceBlob(BaseModel):
    model_config = {"frozen": True}

    path: Path
    media_type: str
    filename: str


class SampleSnapshotReadService:
    """Owns database reads and DTO shaping for run API endpoints."""

    def list_samples(
        self,
        *,
        limit: int = 20,
        status: str | None = None,
        definition_id: UUID | None = None,
        experiment: str | None = None,
        offset: int = 0,
    ) -> list[SampleSummaryDto]:
        with get_session() as session:
            stmt = select(SampleRecord).order_by(col(SampleRecord.created_at).desc())
            if status:
                stmt = stmt.where(SampleRecord.status == status)
            if definition_id:
                stmt = stmt.where(SampleRecord.definition_id == definition_id)
            if experiment:
                stmt = stmt.where(SampleRecord.experiment == experiment)
            stmt = stmt.offset(offset).limit(limit)
            rows = list(session.exec(stmt).all())
            definition_ids = [row.definition_id for row in rows if row.definition_id is not None]
            definition_names = {
                definition.id: definition.name
                for definition in session.exec(
                    select(ExperimentDefinition).where(
                        col(ExperimentDefinition.id).in_(definition_ids)
                    )
                ).all()
            }
            task_counts = _task_counts_by_sample(session, [row.id for row in rows])
        return [
            _run_summary(
                row,
                definition_name=(
                    definition_names.get(row.definition_id)
                    if row.definition_id is not None
                    else None
                ),
                task_counts=task_counts.get(row.id),
            )
            for row in rows
        ]

    def get_sample_summary(self, sample_id: UUID) -> SampleSummaryDto | None:
        with get_session() as session:
            run = session.get(SampleRecord, sample_id)
        return _run_summary(run) if run is not None else None

    def build_snapshot(self, sample_id: UUID) -> SampleSnapshotDto | None:
        with get_session() as session:
            run = session.get(SampleRecord, sample_id)
            if run is None:
                return None

            definition = (
                session.get(ExperimentDefinition, run.definition_id)
                if run.definition_id is not None
                else None
            )
            nodes = list(
                session.exec(
                    select(SampleGraphNode).where(SampleGraphNode.sample_id == sample_id)
                ).all()
            )
            edges = list(
                session.exec(
                    select(SampleGraphEdge).where(SampleGraphEdge.sample_id == sample_id)
                ).all()
            )
            def_workers = (
                list(
                    session.exec(
                        select(ExperimentDefinitionWorker).where(
                            ExperimentDefinitionWorker.experiment_definition_id == run.definition_id
                        )
                    ).all()
                )
                if run.definition_id is not None
                else []
            )
            executions = list(
                session.exec(
                    select(SampleTaskAttempt).where(SampleTaskAttempt.sample_id == sample_id)
                ).all()
            )
            resources = list(
                session.exec(
                    select(SampleResource).where(SampleResource.sample_id == sample_id)
                ).all()
            )
            evaluations = list(
                session.exec(
                    select(SampleTaskEvaluation).where(SampleTaskEvaluation.sample_id == sample_id)
                ).all()
            )
            threads = list(session.exec(select(Thread).where(Thread.sample_id == sample_id)).all())
            thread_messages = list(
                session.exec(
                    select(ThreadMessage).where(ThreadMessage.sample_id == sample_id)
                ).all()
            )
            context_events = list(
                session.exec(
                    select(SampleContextEvent)
                    .where(SampleContextEvent.sample_id == sample_id)
                    .order_by(
                        col(SampleContextEvent.task_execution_id),
                        col(SampleContextEvent.sequence),
                    )
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

        score_summary = EvaluationService.summarize_scores(evaluations)

        duration_seconds: float | None = None
        if run.started_at and run.completed_at:
            duration_seconds = (run.completed_at - run.started_at).total_seconds()

        sample_id_str = str(run.id)
        run_summary = run.parsed_summary()
        aggregated_metrics = aggregate_run_metrics(context_events, summary=run_summary)
        assignment = run.parsed_assignment()
        meta = definition.parsed_metadata() if definition is not None else assignment
        run_name = str(
            run_summary.get("name")
            or assignment.get("sample_name")
            or meta.get("name")
            or run.benchmark_type
        )

        return SampleSnapshotDto(
            id=sample_id_str,
            definition_id=str(run.definition_id) if run.definition_id is not None else None,
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
                sample_id_str,
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
            final_score=_display_run_score(score_summary, run.status, run_summary),
            metrics=SampleSnapshotMetricsDto(
                sample_id=sample_id_str,
                status=str(run.status),
                duration_ms=(
                    round(duration_seconds * 1000) if duration_seconds is not None else None
                ),
                total_tasks=total_tasks,
                tool_call_count=aggregated_metrics.tool_call_count,
                total_tokens=aggregated_metrics.total_tokens,
                token_breakdown=aggregated_metrics.token_breakdown,
                total_cost_usd=aggregated_metrics.total_cost_usd,
                cost_observed=aggregated_metrics.cost_observed,
            ),
            error=run.error_message,
        )

    def list_events(self, sample_id: UUID) -> list[SampleRuntimeEventView] | None:
        with get_session() as session:
            run = session.get(SampleRecord, sample_id)
            if run is None:
                return None
            return SampleRuntimeEventReadService().list_events(session, sample_id)

    def get_resource_blob(self, sample_id: UUID, resource_id: UUID) -> SampleResourceBlob | None:
        with get_session() as session:
            resource = session.exec(
                select(SampleResource).where(
                    SampleResource.id == resource_id,
                    SampleResource.sample_id == sample_id,
                )
            ).first()

        if resource is None or resource.file_path is None:
            return None

        blob_path = Path(resource.file_path).resolve(strict=True)
        blob_path.relative_to(_blob_root())
        size = blob_path.stat().st_size
        require_viewable_resource_size(size)
        return SampleResourceBlob(
            path=blob_path,
            media_type=resource.mime_type or "application/octet-stream",
            filename=resource.name,
        )


class SampleReadService:
    """Sample-centered read service backed by typed WAL and graph projections."""

    def __init__(self, session: Session | None = None) -> None:
        self._session = session

    def get_sample_detail(self, sample_id: UUID) -> SampleDetailView | None:
        with self._session_scope() as session:
            sample = session.get(SampleRecord, sample_id)
            if sample is None:
                return None
            environment = _sample_environment(session, sample)
            return _sample_detail_view(sample, environment_name=environment.name)

    def list_sample_events(self, sample_id: UUID) -> SampleEventsView | None:
        with self._session_scope() as session:
            if session.get(SampleRecord, sample_id) is None:
                return None
            events = SampleRuntimeEventReadService().list_events(session, sample_id)
            return SampleEventsView(items=[_sample_event_view(event) for event in events])

    def get_sample_graph(self, sample_id: UUID) -> SampleGraphView | None:
        with self._session_scope() as session:
            if session.get(SampleRecord, sample_id) is None:
                return None
            return _sample_graph_view(session, sample_id)

    def get_sample_state(self, sample_id: UUID) -> SampleStateView | None:
        with self._session_scope() as session:
            sample = session.get(SampleRecord, sample_id)
            if sample is None:
                return None
            environment = _sample_environment(session, sample)
            detail = _sample_detail_view(sample, environment_name=environment.name)
            events = SampleRuntimeEventReadService().list_events(session, sample_id)
            graph = _sample_graph_view(session, sample_id)
            return SampleStateView(
                sample_id=sample.id,
                experiment_id=detail.experiment_id,
                environment_id=detail.environment_id,
                environment_name=detail.environment_name,
                detail=detail,
                events=[_sample_event_view(event) for event in events],
                graph=graph,
            )

    def _session_scope(self) -> AbstractContextManager[Session]:
        if self._session is not None:
            return _ExistingSessionScope(self._session)
        return get_session()


class _ExistingSessionScope:
    def __init__(self, session: Session) -> None:
        self._session = session

    def __enter__(self) -> Session:
        return self._session

    def __exit__(self, *args: object) -> None:
        return None


def _sample_environment(session: Session, sample: SampleRecord) -> ExperimentEnvironmentRow:
    if sample.environment_id is None:
        raise ValueError(f"Sample {sample.id} is missing environment provenance")
    environment = session.get(ExperimentEnvironmentRow, sample.environment_id)
    if environment is None:
        raise ValueError(f"Sample {sample.id} points at missing environment {sample.environment_id}")
    return environment


def _sample_detail_view(
    sample: SampleRecord,
    *,
    environment_name: str,
) -> SampleDetailView:
    if sample.experiment_id is None or sample.environment_id is None:
        raise ValueError(f"Sample {sample.id} is missing experiment/environment provenance")
    assignment = sample.parsed_assignment()
    source_metadata = assignment.get("source_metadata", {})
    return SampleDetailView(
        sample_id=sample.id,
        experiment_id=sample.experiment_id,
        environment_id=sample.environment_id,
        environment_name=environment_name,
        sample_key=sample.sample_key or sample.instance_key,
        sample_ref=sample.sample_ref_json,
        source_metadata=source_metadata if isinstance(source_metadata, dict) else {},
        status=str(sample.status),
        created_at=sample.created_at,
        started_at=sample.started_at,
        completed_at=sample.completed_at,
    )


def _sample_event_view(event: SampleRuntimeEventView) -> SampleEventView:
    return SampleEventView(
        event_id=event.id,
        sample_id=event.sample_id,
        event_type=event.event_type,
        target_type=event.target_type,
        target_id=event.target_id,
        timestamp=event.event_timestamp,
        payload=event.payload,
    )


def _sample_graph_view(session: Session, sample_id: UUID) -> SampleGraphView:
    nodes = list(
        session.exec(
            select(SampleGraphNode)
            .where(SampleGraphNode.sample_id == sample_id)
            .order_by(col(SampleGraphNode.created_at), col(SampleGraphNode.task_id))
        ).all()
    )
    edges = list(
        session.exec(
            select(SampleGraphEdge)
            .where(SampleGraphEdge.sample_id == sample_id)
            .order_by(col(SampleGraphEdge.created_at), col(SampleGraphEdge.id))
        ).all()
    )
    return SampleGraphView(
        nodes=[
            SampleGraphNodeView(
                task_id=node.task_id,
                task_slug=node.task_slug,
                description=node.description,
                status=str(node.status),
                parent_task_id=node.parent_task_id,
                level=node.level,
                assigned_worker_slug=node.assigned_worker_slug,
                created_at=node.created_at,
                updated_at=node.updated_at,
            )
            for node in nodes
        ],
        edges=[
            SampleGraphEdgeView(
                edge_id=edge.id,
                source_task_id=edge.source_task_id,
                target_task_id=edge.target_task_id,
                status=str(edge.status),
                created_at=edge.created_at,
                updated_at=edge.updated_at,
            )
            for edge in edges
        ],
    )


def _display_run_score(
    score_summary: EvaluationScoreSummary,
    run_status: str,
    summary: dict,
) -> float | None:
    persisted_score = _summary_number(summary, "normalized_score")
    if persisted_score is None:
        persisted_score = _summary_number(summary, "final_score")
    if persisted_score is None:
        persisted_score = _summary_number(summary, "score")
    if run_status != SampleStatus.COMPLETED:
        return persisted_score
    # TODO: this is a hack, we need to fix the calculation / rename variables to make clear that the output score should be normalised by here.
    return (
        score_summary.normalized_score
        if score_summary.normalized_score is not None
        else persisted_score
    )


def _run_summary(
    run: SampleRecord,
    *,
    definition_name: str | None = None,
    task_counts: dict[str, object] | None = None,
) -> SampleSummaryDto:
    summary = run.parsed_summary()
    metrics = summary.get("metrics")
    total_cost_usd, _ = observed_cost_from_summary(summary)
    return SampleSummaryDto(
        id=run.id,
        name=_summary_text(summary, "name")
        or _summary_text(summary, "run_name")
        or f"{run.benchmark_type} / {run.instance_key}",
        status=str(run.status),
        created_at=run.created_at,
        started_at=run.started_at,
        completed_at=run.completed_at,
        latest_activity_at=_latest_activity(run, task_counts),
        duration_seconds=_duration_seconds(run),
        definition_id=run.definition_id,
        definition_name=definition_name,
        experiment=run.experiment,
        benchmark_type=run.benchmark_type,
        instance_key=run.instance_key,
        sample_id=run.sample_id,
        sample_label=run.sample_id or run.instance_key,
        evaluator_slug=run.evaluator_slug,
        model_target=run.model_target,
        final_score=_summary_number(summary, "normalized_score")
        or _summary_number(summary, "final_score")
        or _summary_number(summary, "score"),
        return_value=_summary_number(summary, "return") or _summary_number(summary, "return_value"),
        total_tasks=_count_value(task_counts, "total"),
        completed_tasks=_count_value(task_counts, "completed"),
        failed_tasks=_count_value(task_counts, "failed"),
        running_tasks=_count_value(task_counts, "running"),
        cancelled_tasks=_count_value(task_counts, "cancelled"),
        total_cost_usd=total_cost_usd,
        error_message=run.error_message or _summary_text(summary, "error_message"),
        metrics=dict(metrics) if isinstance(metrics, dict) else {},
    )


def _task_counts_by_sample(
    session: Session, sample_ids: list[UUID]
) -> dict[UUID, dict[str, object]]:
    counts: dict[UUID, dict[str, int]] = {
        sample_id: {
            "total": 0,
            "completed": 0,
            "failed": 0,
            "running": 0,
            "cancelled": 0,
        }
        for sample_id in sample_ids
    }
    if not sample_ids:
        return {}

    nodes = list(
        session.exec(
            select(SampleGraphNode).where(col(SampleGraphNode.sample_id).in_(sample_ids))
        ).all()
    )
    latest_updates: dict[UUID, datetime] = {}
    for node in nodes:
        run_counts = counts.setdefault(
            node.sample_id,
            {"total": 0, "completed": 0, "failed": 0, "running": 0, "cancelled": 0},
        )
        run_counts["total"] += 1
        status = str(node.status)
        if status in run_counts:
            run_counts[status] += 1
        elif status in {"executing", "evaluating"}:
            run_counts["running"] += 1
        if node.updated_at is not None:
            latest_updates[node.sample_id] = max(
                latest_updates.get(node.sample_id, node.updated_at),
                node.updated_at,
            )

    result: dict[UUID, dict[str, object]] = {
        sample_id: dict(run_counts) for sample_id, run_counts in counts.items()
    }
    for sample_id, updated_at in latest_updates.items():
        result[sample_id]["latest_update"] = updated_at
    return result


def _count_value(task_counts: dict[str, object] | None, key: str) -> int:
    value = (task_counts or {}).get(key, 0)
    return value if isinstance(value, int) else 0


def _latest_activity(run: SampleRecord, task_counts: dict | None = None) -> datetime | None:
    candidates = [run.created_at, run.started_at, run.completed_at]
    latest_update = (task_counts or {}).get("latest_update")
    if isinstance(latest_update, datetime):
        candidates.append(latest_update)
    return max(value for value in candidates if value is not None)


def _duration_seconds(run: SampleRecord) -> float | None:
    if run.started_at is None or run.completed_at is None:
        return None
    return (run.completed_at - run.started_at).total_seconds()


def _summary_number(summary: dict, key: str) -> float | None:
    value = summary.get(key)
    if isinstance(value, int | float):
        return float(value)
    return None


def _summary_text(summary: dict, key: str) -> str | None:
    value = summary.get(key)
    if isinstance(value, str) and value:
        return value
    return None


def _blob_root() -> Path:
    return (
        Path(os.environ.get("ERGON_BLOB_ROOT", "/var/ergon/blob")).resolve()
    )  # TODO: this should be set in pydantic-settings, not with this os fallback we dont ever set
