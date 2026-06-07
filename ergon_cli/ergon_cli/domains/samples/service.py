from ergon_cli.domains.samples.models import (
    ListSamplesCommand,
    SampleListResult,
    SampleDetailCliState,
    SampleEventCliState,
    SampleEventsCommand,
    SampleGraphCliState,
    SampleGraphCommand,
    SampleStatusCommand,
    SampleSummaryView,
)
from ergon_cli.shared.errors import CliNotFoundError
from ergon_core.core.views.samples.models import SampleSummaryDto
from ergon_core.core.views.samples.service import SampleReadService, SampleSnapshotReadService


def list_samples(
    command: ListSamplesCommand, *, read_service: SampleSnapshotReadService | None = None
) -> SampleListResult:
    service = read_service or SampleSnapshotReadService()
    rows = service.list_samples(
        limit=command.limit,
        status=command.status,
        experiment=command.experiment,
    )
    return SampleListResult(
        samples=tuple(_view(row) for row in rows),
        status=command.status,
        experiment=command.experiment,
    )


def get_sample_status(
    command: SampleStatusCommand,
    *,
    read_service: SampleSnapshotReadService | None = None,
) -> SampleSummaryView:
    service = read_service or SampleSnapshotReadService()
    row = service.get_sample_summary(command.sample_id)
    if row is None:
        raise CliNotFoundError(f"No sample found with id {command.sample_id}")
    return _view(row)


def get_sample_detail(
    command: SampleStatusCommand,
    *,
    read_service: SampleReadService | None = None,
) -> SampleDetailCliState:
    service = read_service or SampleReadService()
    row = service.get_sample_detail(command.sample_id)
    if row is None:
        raise CliNotFoundError(f"No sample found with id {command.sample_id}")
    return SampleDetailCliState(
        sample_id=row.sample_id,
        experiment_id=row.experiment_id,
        environment_id=row.environment_id,
        environment_name=row.environment_name,
        sample_key=row.sample_key,
        status=row.status,
    )


def list_sample_events(
    command: SampleEventsCommand,
    *,
    read_service: SampleReadService | None = None,
) -> tuple[SampleEventCliState, ...]:
    service = read_service or SampleReadService()
    events = service.list_sample_events(command.sample_id)
    if events is None:
        raise CliNotFoundError(f"No sample found with id {command.sample_id}")
    return tuple(
        SampleEventCliState(
            event_type=event.event_type,
            target=event.target_type,
            timestamp=event.timestamp.isoformat(),
        )
        for event in events.items
    )


def get_sample_graph(
    command: SampleGraphCommand,
    *,
    read_service: SampleReadService | None = None,
) -> SampleGraphCliState:
    service = read_service or SampleReadService()
    graph = service.get_sample_graph(command.sample_id)
    if graph is None:
        raise CliNotFoundError(f"No sample found with id {command.sample_id}")
    return SampleGraphCliState(
        node_count=len(graph.nodes),
        edge_count=len(graph.edges),
        nodes=tuple(f"{node.task_slug}\t{node.status}" for node in graph.nodes),
    )


def _view(row: SampleSummaryDto) -> SampleSummaryView:
    created = row.created_at.strftime("%Y-%m-%d %H:%M") if row.created_at else "-"
    started = row.started_at.strftime("%Y-%m-%d %H:%M:%S") if row.started_at else None
    completed = row.completed_at.strftime("%Y-%m-%d %H:%M:%S") if row.completed_at else None
    duration = ""
    if row.started_at and row.completed_at:
        delta = row.completed_at - row.started_at
        duration = f"{int(delta.total_seconds())}s"
    return SampleSummaryView(
        id=row.id,
        status=row.status,
        created=created,
        started=started,
        completed=completed,
        duration=duration,
        benchmark_type=row.benchmark_type,
        instance_key=row.instance_key,
        evaluator_slug=row.evaluator_slug,
        model_target=row.model_target,
        error_message=row.error_message,
    )
