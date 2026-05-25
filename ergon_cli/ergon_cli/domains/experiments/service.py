from ergon_cli.domains.experiments.models import (
    ExperimentDetailView,
    ExperimentRunView,
    ExperimentSummaryView,
    ExperimentTagDefinitionView,
    ListByTagCommand,
    ListExperimentsCommand,
    ListTagsCommand,
    ShowExperimentCommand,
)
from ergon_cli.shared.errors import CliNotFoundError
from ergon_core.core.views.experiments.models import ExperimentDetailDto, ExperimentSummaryDto
from ergon_core.core.views.experiments.service import ExperimentReadService


def list_experiments(
    command: ListExperimentsCommand,
    *,
    read_service: ExperimentReadService | None = None,
) -> list[ExperimentSummaryView]:
    service = read_service or ExperimentReadService()
    return [_summary_view(row) for row in service.list_experiments(limit=command.limit)]


def show_experiment(
    command: ShowExperimentCommand,
    *,
    read_service: ExperimentReadService | None = None,
) -> ExperimentDetailView:
    service = read_service or ExperimentReadService()
    detail = service.get_experiment(command.definition_id)
    if detail is None:
        raise CliNotFoundError(f"Experiment not found: {command.definition_id}")
    return _detail_view(detail)


def list_tags(
    command: ListTagsCommand,
    *,
    read_service: ExperimentReadService | None = None,
) -> list[str]:
    del command
    service = read_service or ExperimentReadService()
    return service.distinct_tags()


def list_by_tag(
    command: ListByTagCommand,
    *,
    read_service: ExperimentReadService | None = None,
) -> list[ExperimentTagDefinitionView]:
    service = read_service or ExperimentReadService()
    return [
        ExperimentTagDefinitionView(
            definition_id=row.definition_id,
            name=row.name,
            benchmark_type=row.benchmark_type,
            latest_run_status=row.latest_run_status,
        )
        for row in service.definitions_by_tag(command.tag)
    ]


def _summary_view(row: ExperimentSummaryDto) -> ExperimentSummaryView:
    return ExperimentSummaryView(
        definition_id=row.definition_id,
        name=row.name,
        benchmark_type=row.benchmark_type,
        status=row.status,
        sample_count=row.sample_count,
        run_count=row.run_count,
        default_model_target=row.default_model_target,
        default_evaluator_slug=row.default_evaluator_slug,
    )


def _detail_view(detail: ExperimentDetailDto) -> ExperimentDetailView:
    return ExperimentDetailView(
        experiment=_summary_view(detail.experiment),
        sample_selection=detail.sample_selection,
        runs=tuple(
            ExperimentRunView(
                sample_id=run.sample_id,
                instance_key=run.instance_key,
                status=run.status,
                model_target=run.model_target,
            )
            for run in detail.runs
        ),
    )
