from ergon_cli.domains.runs.models import (
    CancelRunCommand,
    CancelRunResult,
    ListRunsCommand,
    RunListResult,
    RunStatusCommand,
    RunSummaryView,
)
from ergon_cli.shared.errors import CliNotFoundError
from ergon_core.core.application.runtime.run_records import cancel_run
from ergon_core.core.views.runs.models import RunSummaryDto
from ergon_core.core.views.runs.service import RunReadService


def list_runs(
    command: ListRunsCommand, *, read_service: RunReadService | None = None
) -> RunListResult:
    service = read_service or RunReadService()
    rows = service.list_runs(
        limit=command.limit,
        status=command.status,
        definition_id=command.definition_id,
        experiment=command.experiment,
    )
    return RunListResult(
        runs=tuple(_view(row) for row in rows),
        status=command.status,
        definition_id=command.definition_id,
        experiment=command.experiment,
    )


def get_run_status(
    command: RunStatusCommand,
    *,
    read_service: RunReadService | None = None,
) -> RunSummaryView:
    service = read_service or RunReadService()
    row = service.get_run_summary(command.run_id)
    if row is None:
        raise CliNotFoundError(f"No run found with id {command.run_id}")
    return _view(row)


def cancel_existing_run(command: CancelRunCommand) -> CancelRunResult:
    try:
        run = cancel_run(command.run_id)
    except ValueError as exc:
        raise CliNotFoundError(f"Error: {exc}") from exc
    return CancelRunResult(run=_view(RunSummaryDto.model_validate(run, from_attributes=True)))


def _view(row: RunSummaryDto) -> RunSummaryView:
    created = row.created_at.strftime("%Y-%m-%d %H:%M") if row.created_at else "-"
    started = row.started_at.strftime("%Y-%m-%d %H:%M:%S") if row.started_at else None
    completed = row.completed_at.strftime("%Y-%m-%d %H:%M:%S") if row.completed_at else None
    duration = ""
    if row.started_at and row.completed_at:
        delta = row.completed_at - row.started_at
        duration = f"{int(delta.total_seconds())}s"
    return RunSummaryView(
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
