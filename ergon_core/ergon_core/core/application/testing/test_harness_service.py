"""Application-side helpers for the danger-prefixed REST test harness."""

from collections.abc import Iterator
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import or_
from ergon_core.core.persistence.context.models import SampleContextEvent
from ergon_core.core.persistence.experiments.models import ExperimentRow
from ergon_core.core.persistence.graph.models import SampleGraphNode
from ergon_core.core.persistence.shared.db import get_engine
from ergon_core.core.persistence.shared.enums import SampleStatus
from ergon_core.core.persistence.telemetry.models import (
    SampleRecord,
    SampleResource,
    SampleTaskEvaluation,
    SampleTaskAttempt,
    Thread,
)
from ergon_core.core.application.samples.events import SampleRuntimeEventReadService
from sqlmodel import Session, select


class UnknownSampleStatusError(ValueError):
    """Raised when a test seed request names an unknown sample status."""


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
class HarnessSampleRuntimeEvent:
    table: str
    event_type: str
    target_id: UUID | None
    payload: dict


@dataclass(frozen=True)
class HarnessExecution:
    task_slug: str | None
    status: str
    error: str | None


@dataclass(frozen=True)
class HarnessSampleState:
    sample_id: UUID
    status: str
    graph_nodes: list[HarnessGraphNode]
    events: list[HarnessSampleRuntimeEvent]
    evaluations: list[HarnessEvaluation]
    executions: list[HarnessExecution]
    execution_count: int
    event_count: int
    resource_count: int
    thread_count: int
    context_event_count: int


@dataclass(frozen=True)
class HarnessExperimentSample:
    sample_id: UUID
    status: str


def get_session_dep() -> Iterator[Session]:
    """Session-factory dependency for the test harness routes."""
    with Session(get_engine()) as session:
        yield session


def read_sample_state(sample_id: UUID, session: Session) -> HarnessSampleState | None:
    sample = session.exec(select(SampleRecord).where(SampleRecord.id == sample_id)).first()
    if sample is None:
        return None

    nodes = list(
        session.exec(select(SampleGraphNode).where(SampleGraphNode.sample_id == sample_id)).all()
    )
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

    event_rows = SampleRuntimeEventReadService().list_events(session, sample_id)
    events = [
        HarnessSampleRuntimeEvent(
            table=_sample_runtime_event_table(event.event_type),
            event_type=event.event_type,
            target_id=event.target_id,
            payload=dict(event.payload),
        )
        for event in event_rows
    ]

    eval_rows = list(
        session.exec(
            select(SampleTaskEvaluation).where(SampleTaskEvaluation.sample_id == sample_id)
        ).all()
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
        session.exec(
            select(SampleTaskAttempt).where(SampleTaskAttempt.sample_id == sample_id)
        ).all()
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
        list(
            session.exec(select(SampleResource).where(SampleResource.sample_id == sample_id)).all()
        )
    )
    thread_count = len(
        list(session.exec(select(Thread).where(Thread.sample_id == sample_id)).all())
    )
    context_event_count = len(
        list(
            session.exec(
                select(SampleContextEvent).where(SampleContextEvent.sample_id == sample_id)
            ).all()
        )
    )

    return HarnessSampleState(
        sample_id=sample_id,
        status=sample.status,
        graph_nodes=graph_nodes,
        events=events,
        evaluations=evaluations,
        executions=executions,
        execution_count=len(execution_rows),
        event_count=len(event_rows),
        resource_count=resource_count,
        thread_count=thread_count,
        context_event_count=context_event_count,
    )


def read_experiment_samples(experiment: str, session: Session) -> list[HarnessExperimentSample]:
    samples = list(
        session.exec(
            select(SampleRecord)
            .join(ExperimentRow, SampleRecord.experiment_id == ExperimentRow.id, isouter=True)
            .where(or_(SampleRecord.experiment == experiment, ExperimentRow.name == experiment))
        ).all(),
    )
    return [
        HarnessExperimentSample(sample_id=sample.id, status=sample.status) for sample in samples
    ]


def seed_sample(
    *,
    benchmark_type: str,
    instance_key: str,
    worker_team: dict,
    experiment: str,
    status: str,
    task_slugs: list[str],
) -> UUID:
    try:
        sample_status = SampleStatus(status)
    except ValueError as exc:
        raise UnknownSampleStatusError(status) from exc

    with Session(get_engine()) as session:
        sample = SampleRecord(
            benchmark_type=benchmark_type,
            instance_key=instance_key,
            worker_team_json=worker_team,
            experiment=experiment,
            status=sample_status,
            summary_json={
                "_test_seeded": True,
                "_test_experiment": experiment,
                "_test_task_slugs": task_slugs,
            },
        )
        session.add(sample)
        session.commit()
        session.refresh(sample)
        return sample.id


def reset_test_rows(*, experiment_prefix: str) -> None:
    with Session(get_engine()) as session:
        # Cannot SQL-filter on JSON prefix portably; load seeded rows and
        # filter in Python. Bounded by the seed endpoint being test-only.
        candidates = list(session.exec(select(SampleRecord)).all())
        for sample in candidates:
            metadata = {} if sample.summary_json is None else sample.summary_json
            if not metadata.get("_test_seeded"):
                continue
            tag = metadata.get("_test_experiment")
            if isinstance(tag, str) and tag.startswith(experiment_prefix):
                session.delete(sample)
        session.commit()


def _execution_error_message(execution: SampleTaskAttempt) -> str | None:
    error = execution.parsed_error()
    if error is None:
        return None
    for key in ("message", "error", "detail"):
        value = error.get(key)
        if isinstance(value, str):
            return value
    return str(error)


def _sample_runtime_event_table(event_type: str) -> str:
    prefix = event_type.split(".", maxsplit=1)[0]
    table_by_prefix = {
        "sample": "sample_status_events",
        "task": "sample_task_events",
        "edge": "sample_edge_events",
        "worker": "sample_worker_events",
        "evaluator": "sample_evaluator_events",
        "sandbox": "sample_sandbox_events",
        "annotation": "sample_annotation_events",
    }
    try:
        return table_by_prefix[prefix]
    except KeyError as exc:
        raise ValueError(f"unknown sample runtime event type: {event_type!r}") from exc
