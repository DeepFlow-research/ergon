"""Application service for experiment cohort queries and resolution."""

from uuid import UUID

from h_arcane.core.persistence.shared.db import get_session
from h_arcane.core.persistence.telemetry.models import (
    ExperimentCohort,
    ExperimentCohortStats,
    ExperimentCohortStatus,
    RunRecord,
)
from h_arcane.core.runtime.services.cohort_schemas import (
    CohortDetailDto,
    CohortRunRowDto,
    CohortStatusCountsDto,
    CohortSummaryDto,
    UpdateCohortRequest,
)
from h_arcane.core.utils import utcnow
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
        """Get a cohort detail DTO with all current run rows."""
        with get_session() as session:
            cohort = session.get(ExperimentCohort, cohort_id)
            if cohort is None:
                return None

            stats = session.exec(
                select(ExperimentCohortStats).where(ExperimentCohortStats.cohort_id == cohort_id)
            ).first()
            summary = self._build_summary(cohort, stats)

            runs = list(
                session.exec(select(RunRecord).where(RunRecord.cohort_id == cohort_id)).all()
            )
            run_rows = [self._build_run_row(cohort, run) for run in runs]
            return CohortDetailDto(summary=summary, runs=run_rows)

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
    def _build_run_row(cohort: ExperimentCohort, run: RunRecord) -> CohortRunRowDto:
        running_time_ms: int | None = None
        if run.started_at is not None:
            end_time = run.completed_at or utcnow()
            running_time_ms = max(int((end_time - run.started_at).total_seconds() * 1000), 0)

        score: float | None = None
        summary = run.parsed_summary()
        if summary:
            score = summary.get("normalized_score") or summary.get("final_score")

        return CohortRunRowDto(
            run_id=run.id,
            definition_id=run.experiment_definition_id,
            cohort_id=cohort.id,
            cohort_name=cohort.name,
            status=run.status,
            created_at=run.created_at,
            started_at=run.started_at,
            completed_at=run.completed_at,
            running_time_ms=running_time_ms,
            final_score=score,
            error_message=run.error_message,
        )


experiment_cohort_service = ExperimentCohortService()
