"""Application-side helpers for the danger-prefixed REST test harness."""

from collections.abc import Iterator
from dataclasses import dataclass
from uuid import UUID

from ergon_core.core.persistence.context.models import RunContextEvent
from ergon_core.core.persistence.definitions.models import ExperimentDefinition
from ergon_core.core.persistence.graph.models import RunGraphMutation, RunGraphNode
from ergon_core.core.persistence.shared.db import get_engine
from ergon_core.core.persistence.shared.enums import RunStatus
from ergon_core.core.persistence.telemetry.models import (
    RunRecord,
    RunResource,
    RunTaskEvaluation,
    RunTaskExecution,
    Thread,
)
from sqlmodel import Session, asc, select


class UnknownRunStatusError(ValueError):
    """Raised when a test seed request names an unknown run status."""


class DefinitionNotFoundError(LookupError):
    """Raised when a test seed request references an unknown definition."""


@dataclass(frozen=True)
class HarnessGraphNode:
    id: UUID
    task_slug: str
    level: int
    status: str
    parent_task_id: UUID | None
    parent_task_slug: str | None


@dataclass(frozen=True)
class HarnessEvaluation:
    task_id: UUID
    task_slug: str | None
    score: float
    reason: str


@dataclass(frozen=True)
class HarnessGraphMutation:
    sequence: int
    mutation_type: str
    target_task_slug: str | None


@dataclass(frozen=True)
class HarnessExecution:
    task_slug: str | None
    status: str
    error: str | None


@dataclass(frozen=True)
class HarnessRunState:
    run_id: UUID
    status: str
    graph_nodes: list[HarnessGraphNode]
    mutations: list[HarnessGraphMutation]
    evaluations: list[HarnessEvaluation]
    executions: list[HarnessExecution]
    execution_count: int
    mutation_count: int
    resource_count: int
    thread_count: int
    context_event_count: int


@dataclass(frozen=True)
class HarnessExperimentRun:
    run_id: UUID
    status: str


def get_session_dep() -> Iterator[Session]:
    """Session-factory dependency for the test harness routes."""
    with Session(get_engine()) as session:
        yield session


def read_run_state(run_id: UUID, session: Session) -> HarnessRunState | None:
    run = session.exec(select(RunRecord).where(RunRecord.id == run_id)).first()
    if run is None:
        return None

    nodes = list(session.exec(select(RunGraphNode).where(RunGraphNode.run_id == run_id)).all())
    slug_by_task_id: dict[UUID, str] = {n.task_id: n.task_slug for n in nodes}

    graph_nodes = [
        HarnessGraphNode(
            id=n.task_id,
            task_slug=n.task_slug,
            level=n.level,
            status=n.status,
            parent_task_id=n.parent_task_id,
            parent_task_slug=(slug_by_task_id.get(n.parent_task_id) if n.parent_task_id else None),
        )
        for n in nodes
    ]

    mutation_rows = list(
        session.exec(
            select(RunGraphMutation)
            .where(RunGraphMutation.run_id == run_id)
            .order_by(asc(RunGraphMutation.sequence))
        ).all()
    )
    mutations = [
        HarnessGraphMutation(
            sequence=m.sequence,
            mutation_type=m.mutation_type,
            target_task_slug=slug_by_task_id.get(m.target_id) if m.target_id else None,
        )
        for m in mutation_rows
    ]

    eval_rows = list(
        session.exec(select(RunTaskEvaluation).where(RunTaskEvaluation.run_id == run_id)).all()
    )
    evaluations = [
        HarnessEvaluation(
            task_id=ev.task_id,
            task_slug=slug_by_task_id.get(ev.task_id),
            score=float(ev.score) if ev.score is not None else 0.0,
            reason="" if ev.feedback is None else ev.feedback,
        )
        for ev in eval_rows
    ]

    execution_rows = list(
        session.exec(select(RunTaskExecution).where(RunTaskExecution.run_id == run_id)).all()
    )
    executions = [
        HarnessExecution(
            task_slug=slug_by_task_id.get(ex.task_id),
            status=ex.status,
            error=_execution_error_message(ex),
        )
        for ex in execution_rows
    ]

    resource_count = len(
        list(session.exec(select(RunResource).where(RunResource.run_id == run_id)).all())
    )
    thread_count = len(list(session.exec(select(Thread).where(Thread.run_id == run_id)).all()))
    context_event_count = len(
        list(session.exec(select(RunContextEvent).where(RunContextEvent.run_id == run_id)).all())
    )

    return HarnessRunState(
        run_id=run_id,
        status=run.status,
        graph_nodes=graph_nodes,
        mutations=mutations,
        evaluations=evaluations,
        executions=executions,
        execution_count=len(execution_rows),
        mutation_count=len(mutation_rows),
        resource_count=resource_count,
        thread_count=thread_count,
        context_event_count=context_event_count,
    )


def read_experiment_runs(experiment: str, session: Session) -> list[HarnessExperimentRun]:
    runs = list(
        session.exec(
            select(RunRecord).where(RunRecord.experiment == experiment)
        ).all(),
    )
    return [HarnessExperimentRun(run_id=r.id, status=r.status) for r in runs]


def seed_run(
    *,
    definition_id: UUID,
    benchmark_type: str,
    instance_key: str,
    worker_team: dict,
    experiment: str,
    status: str,
    task_slugs: list[str],
) -> UUID:
    try:
        run_status = RunStatus(status)
    except ValueError as exc:
        raise UnknownRunStatusError(status) from exc

    with Session(get_engine()) as session:
        definition = session.get(ExperimentDefinition, definition_id)
        if definition is None:
            raise DefinitionNotFoundError(str(definition_id))

        run = RunRecord(
            definition_id=definition_id,
            benchmark_type=benchmark_type,
            instance_key=instance_key,
            worker_team_json=worker_team,
            experiment=experiment,
            status=run_status,
            summary_json={
                "_test_seeded": True,
                "_test_experiment": experiment,
                "_test_task_slugs": task_slugs,
            },
        )
        session.add(run)
        session.commit()
        session.refresh(run)
        return run.id


def reset_test_rows(*, experiment_prefix: str) -> None:
    with Session(get_engine()) as session:
        # Cannot SQL-filter on JSON prefix portably; load seeded rows and
        # filter in Python. Bounded by the seed endpoint being test-only.
        candidates = list(session.exec(select(RunRecord)).all())
        for run in candidates:
            metadata = {} if run.summary_json is None else run.summary_json
            if not metadata.get("_test_seeded"):
                continue
            tag = metadata.get("_test_experiment")
            if isinstance(tag, str) and tag.startswith(experiment_prefix):
                session.delete(run)
        session.commit()


def _execution_error_message(execution: RunTaskExecution) -> str | None:
    error = execution.parsed_error()
    if error is None:
        return None
    for key in ("message", "error", "detail"):
        value = error.get(key)
        if isinstance(value, str):
            return value
    return str(error)
