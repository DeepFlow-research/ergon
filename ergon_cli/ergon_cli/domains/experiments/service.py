from ergon_cli.domains.experiments.models import (
    ExperimentCliState,
    ExperimentDetailView,
    ExperimentEnvironmentCliState,
    ExperimentRunView,
    ExperimentSampleCliState,
    ExperimentSamplesCliResult,
    ExperimentSamplesCommand,
    ExperimentSamplerInvocationsCliResult,
    ExperimentSamplerInvocationsCommand,
    ExperimentSummaryView,
    ExperimentTagDefinitionView,
    ListByTagCommand,
    ListExperimentsCommand,
    ListTagsCommand,
    SamplerInvocationCliState,
    ShowExperimentCommand,
)
from ergon_cli.shared.errors import CliNotFoundError
from ergon_core.core.views.experiments.models import (
    ExperimentDetailDto,
    ExperimentDetailView as CoreExperimentDetailView,
    ExperimentSampleSummaryView,
    ExperimentSummaryDto,
    SamplerInvocationView,
)
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
) -> ExperimentCliState:
    service = read_service or ExperimentReadService()
    detail = service.get_experiment_state(command.experiment_id)
    if detail is None:
        raise CliNotFoundError(f"Experiment not found: {command.experiment_id}")
    return _experiment_state_view(detail)


def list_experiment_samples(
    command: ExperimentSamplesCommand,
    *,
    read_service: ExperimentReadService | None = None,
) -> ExperimentSamplesCliResult:
    service = read_service or ExperimentReadService()
    result = service.list_experiment_samples(command.experiment_id)
    if result is None:
        raise CliNotFoundError(f"Experiment not found: {command.experiment_id}")
    return ExperimentSamplesCliResult(samples=tuple(_sample_view(row) for row in result.items))


def list_experiment_sampler_invocations(
    command: ExperimentSamplerInvocationsCommand,
    *,
    read_service: ExperimentReadService | None = None,
) -> ExperimentSamplerInvocationsCliResult:
    service = read_service or ExperimentReadService()
    result = service.list_sampler_invocations(command.experiment_id)
    if result is None:
        raise CliNotFoundError(f"Experiment not found: {command.experiment_id}")
    return ExperimentSamplerInvocationsCliResult(
        invocations=tuple(_sampler_invocation_view(row) for row in result.items)
    )


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


def _experiment_state_view(detail: CoreExperimentDetailView) -> ExperimentCliState:
    return ExperimentCliState(
        experiment_id=detail.experiment_id,
        name=detail.name,
        environments=tuple(
            ExperimentEnvironmentCliState(
                environment_id=environment.environment_id,
                environment_name=environment.environment_name,
                source_mode=environment.source_mode,
                sample_count=environment.sample_count,
                selected_count=environment.selected_count,
            )
            for environment in detail.environments
        ),
        sample_count=detail.sample_count,
        sampler_invocation_count=len(detail.sampler_invocations),
        samples=tuple(_sample_view(row) for row in detail.samples),
    )


def _sample_view(row: ExperimentSampleSummaryView) -> ExperimentSampleCliState:
    return ExperimentSampleCliState(
        sample_id=row.sample_id,
        environment_name=row.environment_name,
        sample_key=row.sample_key,
        status=row.status,
    )


def _sampler_invocation_view(row: SamplerInvocationView) -> SamplerInvocationCliState:
    return SamplerInvocationCliState(
        sampler_invocation_id=row.sampler_invocation_id,
        sampler_name=row.sampler_name,
        requested_k=row.requested_k,
        candidate_pool_size=row.candidate_pool_size,
        selected_count=row.selected_count,
    )
