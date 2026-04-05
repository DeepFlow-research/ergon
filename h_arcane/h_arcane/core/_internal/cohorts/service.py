"""Application service for experiment cohort queries and resolution."""

from __future__ import annotations

from uuid import UUID

from h_arcane.core._internal.cohorts.schemas import (
    CohortDetailDto,
    CohortMetadataSummaryDto,
    CohortRunRowDto,
    CohortStatusCountsDto,
    CohortSummaryDto,
    ResolveCohortRequest,
    UpdateCohortRequest,
)
from h_arcane.core._internal.db.models import (
    CohortStatsExtras,
    ExperimentCohort,
    ExperimentCohortStatus,
    ExperimentCohortStats,
    Run,
)
from h_arcane.core._internal.db.queries import queries
from h_arcane.core._internal.utils import require_not_none, utcnow


class ExperimentCohortService:
    """Resolve cohorts and assemble frontend-facing cohort DTOs."""

    def resolve_or_create(self, request: ResolveCohortRequest) -> ExperimentCohort:
        """Resolve an existing cohort by name or create it."""
        existing = queries.experiment_cohorts.get_by_name(request.name)
        if existing is not None:
            return existing

        cohort = ExperimentCohort(
            name=request.name,
            description=request.description,
            created_by=request.created_by,
            metadata_json=request.metadata.model_dump(mode="json"),
        )
        return queries.experiment_cohorts.create(cohort)

    def list_summaries(self, *, include_archived: bool = True) -> list[CohortSummaryDto]:
        """List all cohorts as summary DTOs."""
        cohorts = queries.experiment_cohorts.list_all(include_archived=include_archived)
        return [self._build_summary(cohort, queries.experiment_cohort_stats.get(cohort.id)) for cohort in cohorts]

    def get_summary(self, cohort_id: UUID) -> CohortSummaryDto | None:
        """Get a single cohort summary DTO."""
        cohort = queries.experiment_cohorts.get(cohort_id)
        if cohort is None:
            return None
        stats = queries.experiment_cohort_stats.get(cohort_id)
        return self._build_summary(cohort, stats)

    def get_detail(self, cohort_id: UUID) -> CohortDetailDto | None:
        """Get a cohort detail DTO with all current run rows."""
        cohort = queries.experiment_cohorts.get(cohort_id)
        if cohort is None:
            return None

        summary = self._build_summary(cohort, queries.experiment_cohort_stats.get(cohort_id))
        runs = queries.runs.get_by_cohort(cohort_id)
        run_rows = [self._build_run_row(cohort, run) for run in runs]
        return CohortDetailDto(summary=summary, runs=run_rows)

    def update_cohort(self, cohort_id: UUID, request: UpdateCohortRequest) -> CohortSummaryDto | None:
        """Update mutable operator-facing cohort properties."""
        cohort = queries.experiment_cohorts.set_status(cohort_id, request.status)
        if cohort is None:
            return None

        stats = queries.experiment_cohort_stats.get(cohort_id)
        return self._build_summary(cohort, stats)

    def archive(self, cohort_id: UUID) -> CohortSummaryDto | None:
        """Archive a cohort so it disappears from the default operator view."""
        return self.update_cohort(
            cohort_id,
            UpdateCohortRequest(status=ExperimentCohortStatus.ARCHIVED),
        )

    def unarchive(self, cohort_id: UUID) -> CohortSummaryDto | None:
        """Restore an archived cohort back to the active operator view."""
        return self.update_cohort(
            cohort_id,
            UpdateCohortRequest(status=ExperimentCohortStatus.ACTIVE),
        )

    def _build_summary(
        self,
        cohort: ExperimentCohort,
        stats: ExperimentCohortStats | None,
    ) -> CohortSummaryDto:
        """Build a cohort summary DTO from persistence models."""
        metadata = cohort.parsed_metadata()
        stats_extras = stats.parsed_stats_json() if stats is not None else None
        return CohortSummaryDto(
            cohort_id=cohort.id,
            name=cohort.name,
            description=cohort.description,
            created_by=cohort.created_by,
            created_at=cohort.created_at,
            status=cohort.status,
            total_runs=stats.total_runs if stats is not None else 0,
            status_counts=CohortStatusCountsDto(
                pending=stats.pending_runs if stats is not None else 0,
                executing=stats.executing_runs if stats is not None else 0,
                evaluating=stats.evaluating_runs if stats is not None else 0,
                completed=stats.completed_runs if stats is not None else 0,
                failed=stats.failed_runs if stats is not None else 0,
            ),
            average_score=stats.average_score if stats is not None else None,
            best_score=stats.best_score if stats is not None else None,
            worst_score=stats.worst_score if stats is not None else None,
            average_duration_ms=stats.average_duration_ms if stats is not None else None,
            failure_rate=stats.failure_rate if stats is not None else 0.0,
            metadata_summary=CohortMetadataSummaryDto.from_model(metadata),
            stats_updated_at=stats.updated_at if stats is not None else None,
            extras=stats_extras or CohortStatsExtras(),
        )

    def _build_run_row(self, cohort: ExperimentCohort, run: Run) -> CohortRunRowDto:
        """Build one run row DTO for a cohort detail payload."""
        experiment = require_not_none(
            queries.experiments.get(run.experiment_id),
            f"Experiment {run.experiment_id} not found for run {run.id}",
        )
        task_tree = experiment.parsed_task_tree()
        workflow_name = task_tree.name if task_tree is not None else experiment.task_id

        running_time_ms = None
        if run.started_at is not None:
            end_time = run.completed_at or utcnow()
            running_time_ms = max(int((end_time - run.started_at).total_seconds() * 1000), 0)

        return CohortRunRowDto(
            run_id=run.id,
            experiment_id=experiment.id,
            benchmark_name=experiment.benchmark_name,
            experiment_task_id=experiment.task_id,
            workflow_name=workflow_name,
            cohort_id=cohort.id,
            cohort_name=cohort.name,
            status=run.status,
            worker_model=run.worker_model,
            max_questions=run.max_questions,
            created_at=run.created_at,
            started_at=run.started_at,
            completed_at=run.completed_at,
            running_time_ms=running_time_ms,
            final_score=run.final_score,
            normalized_score=run.normalized_score,
            error_message=run.error_message,
        )


experiment_cohort_service = ExperimentCohortService()
