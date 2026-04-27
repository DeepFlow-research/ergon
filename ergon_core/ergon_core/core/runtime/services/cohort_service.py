"""Application service for experiment cohort queries and resolution."""

from collections import Counter, defaultdict
from uuid import UUID

from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.telemetry.evaluation_summary import EvaluationSummary
from ergon_core.core.persistence.telemetry.models import (
    ExperimentCohort,
    ExperimentCohortStats,
    ExperimentCohortStatus,
    RunRecord,
    RunTaskEvaluation,
)
from ergon_core.core.persistence.graph.models import RunGraphNode
from ergon_core.core.runtime.services.cohort_schemas import (
    CohortDetailDto,
    CohortRubricStatusSummaryDto,
    CohortRunRowDto,
    CohortStatusCountsDto,
    CohortSummaryDto,
    UpdateCohortRequest,
)
from ergon_core.core.utils import utcnow
from sqlmodel import func, select


def _rubric_status_summary(
    summaries: list[EvaluationSummary],
) -> CohortRubricStatusSummaryDto:
    """Build a compact rubric status summary for a cohort run row."""
    counts: Counter[str] = Counter()
    evaluator_names: set[str] = set()
    statuses: list[str] = []

    for summary in summaries:
        evaluator_names.add(summary.evaluator_name)
        for criterion in summary.criterion_results:
            counts[criterion.status] += 1
            statuses.append(criterion.status)

    total = len(statuses)
    if total == 0:
        status = "none"
    elif counts["errored"] > 0:
        status = "errored"
    elif counts["failed"] > 0:
        status = "failing"
    elif counts["passed"] > 0 and counts["skipped"] > 0:
        status = "mixed"
    elif counts["skipped"] == total:
        status = "skipped"
    else:
        status = "passing"

    return CohortRubricStatusSummaryDto(
        status=status,
        total_criteria=total,
        passed=counts["passed"],
        failed=counts["failed"],
        errored=counts["errored"],
        skipped=counts["skipped"],
        criterion_statuses=statuses,
        evaluator_names=sorted(evaluator_names),
    )


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
            task_counts = (
                {
                    run_id: count
                    for run_id, count in session.exec(
                        select(RunGraphNode.run_id, func.count(RunGraphNode.id))
                        .where(RunGraphNode.run_id.in_([run.id for run in runs]))
                        .group_by(RunGraphNode.run_id)
                    ).all()
                }
                if runs
                else {}
            )
            evaluations_by_run: defaultdict[UUID, list[EvaluationSummary]] = defaultdict(list)
            if runs:
                evaluations = session.exec(
                    select(RunTaskEvaluation).where(RunTaskEvaluation.run_id.in_([run.id for run in runs]))
                ).all()
                for evaluation in evaluations:
                    evaluations_by_run[evaluation.run_id].append(evaluation.parsed_summary())
            run_rows = [
                self._build_run_row(
                    cohort,
                    run,
                    int(task_counts.get(run.id, 0)) or None,
                    rubric_status_summary=_rubric_status_summary(evaluations_by_run[run.id]),
                )
                for run in runs
            ]
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
    def _build_run_row(
        cohort: ExperimentCohort,
        run: RunRecord,
        total_tasks: int | None = None,
        *,
        rubric_status_summary: CohortRubricStatusSummaryDto,
    ) -> CohortRunRowDto:
        running_time_ms: int | None = None
        if run.started_at is not None:
            end_time = run.completed_at or utcnow()
            running_time_ms = max(int((end_time - run.started_at).total_seconds() * 1000), 0)

        score: float | None = None
        summary = run.parsed_summary()
        if summary:
            raw_score = summary.get("normalized_score")
            if raw_score is None:
                raw_score = summary.get("final_score")
            score = float(raw_score) if isinstance(raw_score, int | float) else None
        total_cost_usd = summary.get("total_cost_usd") if summary else None

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
            total_tasks=total_tasks,
            total_cost_usd=(
                float(total_cost_usd) if isinstance(total_cost_usd, int | float) else None
            ),
            error_message=run.error_message,
            rubric_status_summary=rubric_status_summary,
        )


experiment_cohort_service = ExperimentCohortService()
