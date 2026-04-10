"""Aggregate stats recomputation for experiment cohorts."""

from collections import Counter
from uuid import UUID

from h_arcane.core.persistence.shared.db import get_session
from h_arcane.core.persistence.shared.enums import RunStatus
from h_arcane.core.persistence.telemetry.models import (
    ExperimentCohortStats,
    RunRecord,
)
from h_arcane.core.utils import utcnow
from sqlmodel import select


class ExperimentCohortStatsService:
    """Recompute denormalized cohort stats from cohort-scoped runs."""

    def recompute(self, cohort_id: UUID) -> None:
        """Recompute and persist aggregate stats for one cohort."""
        with get_session() as session:
            runs = list(
                session.exec(select(RunRecord).where(RunRecord.cohort_id == cohort_id)).all()
            )
            status_counts = Counter(run.status for run in runs)

            scored_values: list[float] = [
                s for s in (self._score_value(run) for run in runs) if s is not None
            ]

            durations_ms = [
                int((run.completed_at - run.started_at).total_seconds() * 1000)
                for run in runs
                if run.started_at is not None and run.completed_at is not None
            ]

            total_runs = len(runs)
            failed_runs = status_counts.get(RunStatus.FAILED, 0)

            existing = session.exec(
                select(ExperimentCohortStats).where(ExperimentCohortStats.cohort_id == cohort_id)
            ).first()

            now = utcnow()
            if existing is not None:
                existing.total_runs = total_runs
                existing.completed_runs = status_counts.get(RunStatus.COMPLETED, 0)
                existing.failed_runs = failed_runs
                existing.average_score = (
                    (sum(scored_values) / len(scored_values)) if scored_values else None
                )
                existing.best_score = max(scored_values) if scored_values else None
                existing.worst_score = min(scored_values) if scored_values else None
                existing.average_duration_ms = (
                    (sum(durations_ms) // len(durations_ms)) if durations_ms else None
                )
                existing.failure_rate = (failed_runs / total_runs) if total_runs else 0.0
                existing.updated_at = now
                session.add(existing)
            else:
                stats = ExperimentCohortStats(
                    cohort_id=cohort_id,
                    total_runs=total_runs,
                    completed_runs=status_counts.get(RunStatus.COMPLETED, 0),
                    failed_runs=failed_runs,
                    average_score=(
                        (sum(scored_values) / len(scored_values)) if scored_values else None
                    ),
                    best_score=max(scored_values) if scored_values else None,
                    worst_score=min(scored_values) if scored_values else None,
                    average_duration_ms=(
                        (sum(durations_ms) // len(durations_ms)) if durations_ms else None
                    ),
                    failure_rate=(failed_runs / total_runs) if total_runs else 0.0,
                    updated_at=now,
                )
                session.add(stats)

            session.commit()

    @staticmethod
    def _score_value(run: RunRecord) -> float | None:
        """Choose the score field used for cohort aggregates."""
        summary = run.parsed_summary()
        if not summary:
            return None
        norm = summary.get("normalized_score")
        if norm is not None:
            return float(norm)
        final = summary.get("final_score")
        if final is not None:
            return float(final)
        return None


experiment_cohort_stats_service = ExperimentCohortStatsService()
