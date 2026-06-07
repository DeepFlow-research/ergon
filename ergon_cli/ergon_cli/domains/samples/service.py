from ergon_cli.domains.samples.models import (
    CancelSampleCommand,
    CancelSampleResult,
    ListSamplesCommand,
    SampleListResult,
    SampleStatusCommand,
    SampleSummaryView,
)
from ergon_cli.shared.errors import CliNotFoundError
from ergon_core.core.application.runtime.sample_records import cancel_sample
from ergon_core.core.views.samples.models import SampleSummaryDto
from ergon_core.core.views.samples.service import SampleSnapshotReadService


def list_samples(
    command: ListSamplesCommand, *, read_service: SampleSnapshotReadService | None = None
) -> SampleListResult:
    service = read_service or SampleSnapshotReadService()
    rows = service.list_samples(
        limit=command.limit,
        status=command.status,
        definition_id=command.definition_id,
        experiment=command.experiment,
    )
    return SampleListResult(
        samples=tuple(_view(row) for row in rows),
        status=command.status,
        definition_id=command.definition_id,
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


def cancel_existing_sample(command: CancelSampleCommand) -> CancelSampleResult:
    try:
        sample = cancel_sample(command.sample_id)
    except ValueError as exc:
        raise CliNotFoundError(f"Error: {exc}") from exc
    return CancelSampleResult(
        sample=_view(SampleSummaryDto.model_validate(sample, from_attributes=True))
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
        definition_id=row.definition_id,
        benchmark_type=row.benchmark_type,
        instance_key=row.instance_key,
        evaluator_slug=row.evaluator_slug,
        model_target=row.model_target,
        error_message=row.error_message,
    )
