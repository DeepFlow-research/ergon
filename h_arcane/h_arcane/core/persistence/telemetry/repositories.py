"""Read and write repository for run telemetry tables."""

from datetime import datetime
from uuid import UUID

from h_arcane.core.persistence.shared.enums import RunStatus, TaskExecutionStatus
from h_arcane.core.persistence.shared.ids import new_id
from h_arcane.core.providers.generation import pydantic_ai_format as pa_format
from h_arcane.core.persistence.telemetry.models import (
    RunAction,
    RunGenerationTurn,
    RunRecord,
    RunResource,
    RunTaskEvaluation,
    RunTaskExecution,
    RunTaskStateEvent,
)
from h_arcane.core.utils import utcnow as _utcnow
from sqlmodel import Session, select


class TelemetryRepository:
    """Combined read/write operations for run-scoped telemetry rows."""

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def get_run(self, session: Session, run_id: UUID) -> RunRecord | None:
        return session.get(RunRecord, run_id)

    def get_task_executions(self, session: Session, run_id: UUID) -> list[RunTaskExecution]:
        stmt = select(RunTaskExecution).where(RunTaskExecution.run_id == run_id)
        return list(session.exec(stmt).all())

    def get_task_evaluations(self, session: Session, run_id: UUID) -> list[RunTaskEvaluation]:
        stmt = select(RunTaskEvaluation).where(RunTaskEvaluation.run_id == run_id)
        return list(session.exec(stmt).all())

    def get_state_events(self, session: Session, run_id: UUID) -> list[RunTaskStateEvent]:
        stmt = select(RunTaskStateEvent).where(RunTaskStateEvent.run_id == run_id)
        return list(session.exec(stmt).all())

    def get_actions(self, session: Session, run_id: UUID) -> list[RunAction]:
        stmt = select(RunAction).where(RunAction.run_id == run_id)
        return list(session.exec(stmt).all())

    def get_resources(self, session: Session, run_id: UUID) -> list[RunResource]:
        stmt = select(RunResource).where(RunResource.run_id == run_id)
        return list(session.exec(stmt).all())

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def create_run(
        self,
        session: Session,
        experiment_definition_id: UUID,
        *,
        status: str = RunStatus.PENDING,
    ) -> RunRecord:
        run = RunRecord(
            id=new_id(),
            experiment_definition_id=experiment_definition_id,
            status=status,
            created_at=_utcnow(),
        )
        session.add(run)
        session.flush()
        return run

    def create_task_execution(
        self,
        session: Session,
        *,
        run_id: UUID,
        definition_task_id: UUID,
        definition_worker_id: UUID | None = None,
        attempt_number: int = 1,
        status: str = TaskExecutionStatus.PENDING,
    ) -> RunTaskExecution:
        execution = RunTaskExecution(
            id=new_id(),
            run_id=run_id,
            definition_task_id=definition_task_id,
            definition_worker_id=definition_worker_id,
            attempt_number=attempt_number,
            status=status,
            started_at=_utcnow(),
        )
        session.add(execution)
        session.flush()
        return execution

    def complete_task_execution(
        self,
        session: Session,
        execution_id: UUID,
        *,
        success: bool,
        output_text: str | None = None,
        output_json: dict[str, object] | None = None,
        error_json: dict[str, object] | None = None,
    ) -> RunTaskExecution:
        execution = session.get(RunTaskExecution, execution_id)
        if execution is None:
            raise ValueError(f"RunTaskExecution {execution_id} not found")

        execution.status = TaskExecutionStatus.COMPLETED if success else TaskExecutionStatus.FAILED
        execution.completed_at = _utcnow()
        if output_text is not None:
            execution.output_text = output_text
        if output_json is not None:
            execution.output_json = output_json
        if error_json is not None:
            execution.error_json = error_json

        session.add(execution)
        session.flush()
        return execution

    def create_action(  # slopcop: ignore[max-function-params]
        self,
        session: Session,
        *,
        run_id: UUID,
        task_execution_id: UUID,
        action_num: int,
        action_type: str,
        input_text: str,
        output_text: str | None = None,
        error_json: dict[str, object] | None = None,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
    ) -> RunAction:
        action = RunAction(
            id=new_id(),
            run_id=run_id,
            task_execution_id=task_execution_id,
            action_num=action_num,
            action_type=action_type,
            input_text=input_text,
            output_text=output_text,
            error_json=error_json,
            started_at=started_at or _utcnow(),
            completed_at=completed_at,
        )
        session.add(action)
        session.flush()
        return action

    def create_resource(  # slopcop: ignore[max-function-params]
        self,
        session: Session,
        *,
        run_id: UUID,
        task_execution_id: UUID | None = None,
        kind: str,
        name: str,
        mime_type: str,
        file_path: str,
        size_bytes: int,
        metadata_json: dict[str, object] | None = None,
    ) -> RunResource:
        resource = RunResource(
            id=new_id(),
            run_id=run_id,
            task_execution_id=task_execution_id,
            kind=kind,
            name=name,
            mime_type=mime_type,
            file_path=file_path,
            size_bytes=size_bytes,
            metadata_json=metadata_json or {},
        )
        session.add(resource)
        session.flush()
        return resource

    def record_state_event(
        self,
        session: Session,
        *,
        run_id: UUID,
        definition_task_id: UUID,
        task_execution_id: UUID | None = None,
        event_type: str,
        old_status: str | None = None,
        new_status: str,
        event_metadata: dict[str, object] | None = None,
    ) -> RunTaskStateEvent:
        event = RunTaskStateEvent(
            id=new_id(),
            run_id=run_id,
            definition_task_id=definition_task_id,
            task_execution_id=task_execution_id,
            event_type=event_type,
            old_status=old_status,
            new_status=new_status,
            event_metadata=event_metadata or {},
        )
        session.add(event)
        session.flush()
        return event

    def create_task_evaluation(
        self,
        session: Session,
        *,
        run_id: UUID,
        definition_task_id: UUID,
        definition_evaluator_id: UUID,
        score: float | None = None,
        passed: bool | None = None,
        feedback: str | None = None,
        summary_json: dict[str, object] | None = None,
    ) -> RunTaskEvaluation:
        evaluation = RunTaskEvaluation(
            id=new_id(),
            run_id=run_id,
            definition_task_id=definition_task_id,
            definition_evaluator_id=definition_evaluator_id,
            score=score,
            passed=passed,
            feedback=feedback,
            summary_json=summary_json or {},
        )
        session.add(evaluation)
        session.flush()
        return evaluation


class GenerationTurnRepository:
    """Read/write operations for lossless per-turn generation records."""

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def persist_turns(
        self,
        session: Session,
        *,
        run_id: UUID,
        execution_id: UUID,
        worker_binding_key: str,
        turns: list,
    ) -> list[RunGenerationTurn]:
        """Persist a list of ``GenerationTurn`` objects as DB rows.

        Args:
            turns: list of ``h_arcane.api.generation.GenerationTurn``.
        """
        rows: list[RunGenerationTurn] = []
        for i, turn in enumerate(turns):
            row = RunGenerationTurn(
                id=new_id(),
                run_id=run_id,
                task_execution_id=execution_id,
                worker_binding_key=worker_binding_key,
                turn_index=i,
                raw_request={},
                raw_response=turn.raw_response,
                response_text=pa_format.extract_text(turn.raw_response),
                tool_calls_json=pa_format.extract_tool_calls(turn.raw_response),
                tool_results_json=turn.tool_results or None,
                token_ids_json=None,  # populated by RL extraction via re-tokenization
                logprobs_json=(
                    [lp.model_dump() for lp in turn.logprobs] if turn.logprobs else None
                ),
                policy_version=turn.policy_version,
            )
            session.add(row)
            rows.append(row)
        session.flush()
        return rows

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def get_for_execution(self, session: Session, execution_id: UUID) -> list[RunGenerationTurn]:
        stmt = (
            select(RunGenerationTurn)
            .where(RunGenerationTurn.task_execution_id == execution_id)
            .order_by(RunGenerationTurn.turn_index)
        )
        return list(session.exec(stmt).all())

    def get_for_run(self, session: Session, run_id: UUID) -> list[RunGenerationTurn]:
        stmt = (
            select(RunGenerationTurn)
            .where(RunGenerationTurn.run_id == run_id)
            .order_by(
                RunGenerationTurn.task_execution_id,
                RunGenerationTurn.turn_index,
            )
        )
        return list(session.exec(stmt).all())
