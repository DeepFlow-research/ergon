"""Application service for experiment cohort queries and resolution."""

from uuid import UUID

from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.telemetry.models import (
    ExperimentCohort,
    ExperimentCohortStats,
    ExperimentCohortStatus,
    ExperimentRecord,
    RunRecord,
)
from ergon_core.core.runtime.services.cohort_schemas import (
    CohortDetailDto,
    CohortExperimentRowDto,
    CohortStatusCountsDto,
    CohortSummaryDto,
    UpdateCohortRequest,
)
from ergon_core.core.utils import utcnow
from sqlmodel import select


class ExperimentCohortService:
    """Resolve cohorts and assemble frontend-facing cohort DTOs."""

    def resolve_or_create(
        self,
        name: str,
        description: str | None = None,
        created_by: str | None = None,
    ) -> ExperimentCohort:
        """Resolve an existing cohort by name or create a new one."""
        with get_session() as session:
            stmt = select(ExperimentCohort).where(ExperimentCohort.name == name)
            existing = session.exec(stmt).first()
            if existing is not None:
                return existing

            cohort = ExperimentCohort(
                name=name,
                description=description,
                created_by=created_by,
            )
            session.add(cohort)
            session.commit()
            session.refresh(cohort)
            return cohort

    def list_summaries(self, *, include_archived: bool = False) -> list[CohortSummaryDto]:
        """List all cohorts as summary DTOs."""
        with get_session() as session:
            stmt = select(ExperimentCohort)
            if not include_archived:
                stmt = stmt.where(ExperimentCohort.status != ExperimentCohortStatus.ARCHIVED)
            cohorts = list(session.exec(stmt).all())

            results: list[CohortSummaryDto] = []
            for cohort in cohorts:
                stats = session.exec(
                    select(ExperimentCohortStats).where(
                        ExperimentCohortStats.cohort_id == cohort.id
                    )
                ).first()
                results.append(self._build_summary(cohort, stats))
            return results

    def get_detail(self, cohort_id: UUID) -> CohortDetailDto | None:
        """Get a cohort detail DTO with all experiments in the project folder."""
        with get_session() as session:
            cohort = session.get(ExperimentCohort, cohort_id)
            if cohort is None:
                return None

            stats = session.exec(
                select(ExperimentCohortStats).where(ExperimentCohortStats.cohort_id == cohort_id)
            ).first()
            summary = self._build_summary(cohort, stats)

            experiments = list(
                session.exec(
                    select(ExperimentRecord).where(ExperimentRecord.cohort_id == cohort_id)
                ).all()
            )
            experiment_rows = [
                self._build_experiment_row(
                    experiment,
                    list(
                        session.exec(
                            select(RunRecord).where(RunRecord.experiment_id == experiment.id)
                        ).all()
                    ),
                )
                for experiment in experiments
            ]
            return CohortDetailDto(summary=summary, experiments=experiment_rows)

    def get_summary(self, cohort_id: UUID) -> CohortSummaryDto | None:
        """Get a single cohort summary DTO."""
        with get_session() as session:
            cohort = session.get(ExperimentCohort, cohort_id)
            if cohort is None:
                return None
            stats = session.exec(
                select(ExperimentCohortStats).where(ExperimentCohortStats.cohort_id == cohort_id)
            ).first()
            return self._build_summary(cohort, stats)

    def update_cohort(
        self, cohort_id: UUID, request: UpdateCohortRequest
    ) -> CohortSummaryDto | None:
        """Update mutable operator-facing cohort properties."""
        with get_session() as session:
            cohort = session.get(ExperimentCohort, cohort_id)
            if cohort is None:
                return None

            cohort.status = request.status.value
            cohort.updated_at = utcnow()
            session.add(cohort)
            session.commit()
            session.refresh(cohort)

            stats = session.exec(
                select(ExperimentCohortStats).where(ExperimentCohortStats.cohort_id == cohort_id)
            ).first()
            return self._build_summary(cohort, stats)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_summary(
        cohort: ExperimentCohort,
        stats: ExperimentCohortStats | None,
    ) -> CohortSummaryDto:
        return CohortSummaryDto(
            cohort_id=cohort.id,
            name=cohort.name,
            description=cohort.description,
            created_by=cohort.created_by,
            created_at=cohort.created_at,
            status=cohort.status,
            total_runs=stats.total_runs if stats else 0,
            status_counts=CohortStatusCountsDto(
                completed=stats.completed_runs if stats else 0,
                failed=stats.failed_runs if stats else 0,
            ),
            average_score=stats.average_score if stats else None,
            best_score=stats.best_score if stats else None,
            worst_score=stats.worst_score if stats else None,
            average_duration_ms=stats.average_duration_ms if stats else None,
            failure_rate=stats.failure_rate if stats else 0.0,
            stats_updated_at=stats.updated_at if stats else None,
        )

    @staticmethod
    def _build_experiment_row(
        experiment: ExperimentRecord,
        runs: list[RunRecord],
    ) -> CohortExperimentRowDto:
        score: float | None = None
        total_cost_usd: float | None = None
        for run in runs:
            summary = run.parsed_summary()
            raw_score = summary.get("normalized_score")
            if raw_score is None:
                raw_score = summary.get("final_score")
            if isinstance(raw_score, int | float):
                score = float(raw_score)
            raw_cost = summary.get("total_cost_usd")
            if isinstance(raw_cost, int | float):
                total_cost_usd = (total_cost_usd or 0.0) + float(raw_cost)

        status_counts = CohortStatusCountsDto()
        for run in runs:
            _increment_status_count(status_counts, str(run.status))

        return CohortExperimentRowDto(
            experiment_id=experiment.id,
            name=experiment.name,
            benchmark_type=experiment.benchmark_type,
            sample_count=experiment.sample_count,
            total_runs=len(runs),
            status_counts=status_counts,
            status=_experiment_row_status(experiment.status, status_counts, len(runs)),
            created_at=experiment.created_at,
            default_model_target=experiment.default_model_target,
            default_evaluator_slug=experiment.default_evaluator_slug,
            final_score=score,
            total_cost_usd=total_cost_usd,
            error_message=None,
        )


def _increment_status_count(counts: CohortStatusCountsDto, status: str) -> None:
    match status:
        case "pending":
            counts.pending += 1
        case "executing":
            counts.executing += 1
        case "evaluating":
            counts.evaluating += 1
        case "completed":
            counts.completed += 1
        case "failed":
            counts.failed += 1


def _experiment_row_status(
    experiment_status: str,
    counts: CohortStatusCountsDto,
    total_runs: int,
) -> str:
    if total_runs == 0:
        return experiment_status
    active_runs = counts.pending + counts.executing + counts.evaluating
    if active_runs > 0:
        return experiment_status
    if counts.failed == total_runs:
        return "failed"
    if counts.completed == total_runs:
        return "completed"
    if counts.failed > 0 and counts.completed > 0:
        return "completed_with_failures"
    return experiment_status


experiment_cohort_service = ExperimentCohortService()
