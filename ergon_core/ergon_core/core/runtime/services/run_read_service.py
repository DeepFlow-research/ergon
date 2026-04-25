"""Read service for dashboard/API run snapshots and related views."""

import os
from collections import defaultdict
from pathlib import Path
from statistics import mean
from uuid import UUID

from ergon_core.core.api.schemas import (
    RunGenerationTurnDto,
    RunGraphMutationDto,
    RunSnapshotDto,
    TrainingCurvePointDto,
    TrainingMetricDto,
    TrainingSessionDto,
)
from ergon_core.core.persistence.context.models import RunContextEvent
from ergon_core.core.persistence.definitions.models import (
    ExperimentDefinition,
    ExperimentDefinitionWorker,
)
from ergon_core.core.persistence.graph.models import RunGraphEdge, RunGraphMutation, RunGraphNode
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.telemetry.models import (
    RunGenerationTurn,
    RunRecord,
    RunResource,
    RunTaskEvaluation,
    RunTaskExecution,
    Thread,
    ThreadMessage,
    TrainingMetric,
    TrainingSession,
)
from pydantic import BaseModel
from sqlmodel import select

_RESOURCE_CONTENT_MAX_BYTES: int = 10 * 1024 * 1024


class RunResourceBlob(BaseModel):
    model_config = {"frozen": True}

    path: Path
    media_type: str
    filename: str


class RunReadService:
    """Owns database reads and DTO shaping for run API endpoints."""

    def build_run_snapshot(self, run_id: UUID) -> RunSnapshotDto | None:
        # reason: reuse pure DTO helper functions without moving them in the same slice.
        from ergon_core.core.api import runs as run_api_helpers

        with get_session() as session:
            run = session.get(RunRecord, run_id)
            if run is None:
                return None

            definition = session.get(ExperimentDefinition, run.experiment_definition_id)
            if definition is None:
                return None

            def_id = run.experiment_definition_id
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
            generation_turns = list(
                session.exec(
                    select(RunGenerationTurn)
                    .where(RunGenerationTurn.run_id == run_id)
                    .order_by(
                        RunGenerationTurn.task_execution_id,
                        RunGenerationTurn.turn_index,
                    )
                ).all()
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
        timestamps = run_api_helpers._task_timestamps(executions)
        (
            task_map,
            root_task_id,
            total_tasks,
            total_leaf,
            completed_tasks,
            failed_tasks,
            running_tasks,
            cancelled_tasks,
        ) = run_api_helpers._build_task_map(nodes, edges, worker_by_binding, timestamps)

        execution_task_map: dict[UUID, UUID] = {
            ex.id: ex.node_id for ex in executions if ex.node_id is not None
        }
        defn_to_node: dict[UUID, UUID] = {
            n.definition_task_id: n.id for n in nodes if n.definition_task_id is not None
        }

        generation_turns_by_task: dict[str, list[RunGenerationTurnDto]] = defaultdict(list)
        for turn in generation_turns:
            node_uuid = execution_task_map.get(turn.task_execution_id)
            if node_uuid is None:
                continue
            generation_turns_by_task[str(node_uuid)].append(
                RunGenerationTurnDto(
                    id=str(turn.id),
                    task_execution_id=str(turn.task_execution_id),
                    worker_binding_key=turn.worker_binding_key,
                    turn_index=turn.turn_index,
                    prompt_text=turn.prompt_text,
                    raw_response=turn.raw_response,
                    response_text=turn.response_text,
                    tool_calls=turn.tool_calls_json,
                    tool_results=turn.tool_results_json,
                    policy_version=turn.policy_version,
                    has_logprobs=turn.token_ids_json is not None,
                    created_at=turn.created_at.isoformat() if turn.created_at else None,
                )
            )

        context_events_by_task = run_api_helpers._context_events_by_task(
            context_events,
            execution_task_map,
        )

        final_score: float | None = None
        if evaluations:
            scores = [ev.score for ev in evaluations if ev.score is not None]
            if scores:
                final_score = sum(scores) / len(scores)

        duration_seconds: float | None = None
        if run.started_at and run.completed_at:
            duration_seconds = (run.completed_at - run.started_at).total_seconds()

        run_id_str = str(run.id)
        run_summary = run.parsed_summary()
        meta = definition.parsed_metadata()
        run_name = str(meta.get("name", definition.benchmark_type))

        return RunSnapshotDto(
            id=run_id_str,
            experiment_id=str(def_id),
            name=run_name,
            status=run.status,
            tasks=task_map,
            root_task_id=root_task_id,
            resources_by_task=run_api_helpers._task_keyed_resources(
                resources,
                execution_task_map,
            ),
            executions_by_task=run_api_helpers._task_keyed_executions(
                executions,
                worker_by_id,
            ),
            evaluations_by_task=run_api_helpers._task_keyed_evaluations(
                evaluations,
                run_id_str,
                defn_to_node,
            ),
            generation_turns_by_task=dict(generation_turns_by_task),
            context_events_by_task=dict(context_events_by_task),
            sandboxes_by_task=run_api_helpers._task_keyed_sandboxes(run_summary),
            threads=run_api_helpers._build_communication_threads(threads, thread_messages),
            started_at=run.started_at or run.created_at,
            completed_at=run.completed_at,
            duration_seconds=duration_seconds,
            total_tasks=total_tasks,
            total_leaf_tasks=total_leaf,
            completed_tasks=completed_tasks,
            failed_tasks=failed_tasks,
            running_tasks=running_tasks,
            cancelled_tasks=cancelled_tasks,
            final_score=final_score,
            error=run.error_message,
        )

    def list_mutations(self, run_id: UUID) -> list[RunGraphMutationDto] | None:
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
            RunGraphMutationDto(
                id=str(m.id),
                run_id=str(m.run_id),
                sequence=m.sequence,
                mutation_type=m.mutation_type,
                target_type=m.target_type,
                target_id=str(m.target_id),
                actor=m.actor,
                old_value=m.old_value,
                new_value=m.new_value,
                reason=m.reason,
                created_at=m.created_at.isoformat(),
            )
            for m in mutations
        ]

    def list_generation_turns(
        self,
        run_id: UUID,
        *,
        include_logprobs: bool,
    ) -> list[RunGenerationTurnDto] | None:
        with get_session() as session:
            run = session.get(RunRecord, run_id)
            if run is None:
                return None
            turns = list(
                session.exec(
                    select(RunGenerationTurn)
                    .where(RunGenerationTurn.run_id == run_id)
                    .order_by(
                        RunGenerationTurn.task_execution_id,
                        RunGenerationTurn.turn_index,
                    )
                ).all()
            )

        return [
            RunGenerationTurnDto(
                id=str(turn.id),
                task_execution_id=str(turn.task_execution_id),
                worker_binding_key=turn.worker_binding_key,
                turn_index=turn.turn_index,
                prompt_text=turn.prompt_text,
                raw_response=turn.raw_response,
                response_text=turn.response_text,
                tool_calls=turn.tool_calls_json,
                tool_results=turn.tool_results_json,
                policy_version=turn.policy_version,
                has_logprobs=turn.token_ids_json is not None,
                created_at=turn.created_at.isoformat() if turn.created_at else None,
                token_ids=turn.token_ids_json if include_logprobs else None,
                logprobs=turn.logprobs_json if include_logprobs else None,
            )
            for turn in turns
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
        if size > _RESOURCE_CONTENT_MAX_BYTES:
            raise ValueError(f"resource-too-large:{size}")
        return RunResourceBlob(
            path=blob_path,
            media_type=resource.mime_type or "application/octet-stream",
            filename=resource.name,
        )

    def list_training_curves(
        self,
        *,
        definition_id: UUID | None,
        cohort_id: UUID | None,
    ) -> list[TrainingCurvePointDto]:
        with get_session() as session:
            stmt = select(RunRecord)
            if definition_id:
                stmt = stmt.where(RunRecord.experiment_definition_id == definition_id)
            if cohort_id:
                stmt = stmt.where(RunRecord.cohort_id == cohort_id)
            stmt = stmt.order_by(RunRecord.created_at)
            runs = list(session.exec(stmt).all())

            all_run_ids = [r.id for r in runs]
            evals = list(
                session.exec(
                    select(RunTaskEvaluation).where(RunTaskEvaluation.run_id.in_(all_run_ids))  # type: ignore[union-attr]
                ).all()
            )

        scores_by_run: dict[UUID, list[float]] = defaultdict(list)
        for ev in evals:
            if ev.score is not None:
                scores_by_run[ev.run_id].append(ev.score)

        points: list[TrainingCurvePointDto] = []
        for run in runs:
            summary = run.parsed_summary()
            step = summary.get("checkpoint_step")
            if step is None:
                continue

            run_scores = scores_by_run.get(run.id, [])
            if not run_scores:
                continue

            points.append(
                TrainingCurvePointDto(
                    run_id=str(run.id),
                    step=int(step),
                    mean_score=mean(run_scores),
                    benchmark_type=summary.get("benchmark_type"),
                    created_at=run.created_at.isoformat() if run.created_at else None,
                )
            )

        return points

    def list_training_sessions(
        self,
        *,
        definition_id: UUID | None,
    ) -> list[TrainingSessionDto]:
        with get_session() as session:
            stmt = select(TrainingSession).order_by(TrainingSession.started_at.desc())
            if definition_id:
                stmt = stmt.where(TrainingSession.experiment_definition_id == definition_id)
            sessions = list(session.exec(stmt).all())

        return [
            TrainingSessionDto(
                id=str(s.id),
                experiment_definition_id=str(s.experiment_definition_id),
                model_name=s.model_name,
                status=s.status,
                started_at=s.started_at.isoformat() if s.started_at else None,
                completed_at=s.completed_at.isoformat() if s.completed_at else None,
                output_dir=s.output_dir,
                total_steps=s.total_steps,
                final_loss=s.final_loss,
            )
            for s in sessions
        ]

    def list_training_metrics(self, session_id: UUID) -> list[TrainingMetricDto]:
        with get_session() as session:
            metrics = list(
                session.exec(
                    select(TrainingMetric)
                    .where(TrainingMetric.session_id == session_id)
                    .order_by(TrainingMetric.step)
                ).all()
            )

        return [
            TrainingMetricDto(
                step=m.step,
                epoch=m.epoch,
                loss=m.loss,
                grad_norm=m.grad_norm,
                learning_rate=m.learning_rate,
                reward_mean=m.reward_mean,
                reward_std=m.reward_std,
                entropy=m.entropy,
                completion_mean_length=m.completion_mean_length,
                step_time_s=m.step_time_s,
            )
            for m in metrics
        ]


def _blob_root() -> Path:
    return Path(os.environ.get("ERGON_BLOB_ROOT", "/var/ergon/blob")).resolve()
