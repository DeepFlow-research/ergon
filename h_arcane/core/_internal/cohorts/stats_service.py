"""Aggregate stats recomputation for experiment cohorts."""

from __future__ import annotations

from collections import Counter
from uuid import UUID

from h_arcane.core._internal.db.models import ExperimentCohortStats, Run, RunStatus
from h_arcane.core._internal.db.queries import queries
from h_arcane.core._internal.utils import utcnow


class ExperimentCohortStatsService:
    """Recompute denormalized cohort stats from cohort-scoped runs."""

    def recompute(self, cohort_id: UUID) -> ExperimentCohortStats:
        """Recompute and persist aggregate stats for one cohort."""
        runs = queries.runs.get_by_cohort(cohort_id)
        status_counts = Counter(run.status for run in runs)

        scored_values = [self._score_value(run) for run in runs]
        scored_values = [score for score in scored_values if score is not None]

        durations_ms = [
            int((run.completed_at - run.started_at).total_seconds() * 1000)
            for run in runs
            if run.started_at is not None and run.completed_at is not None
        ]

        benchmark_counts = Counter()
        latest_run_at = None
        for run in runs:
            experiment = queries.experiments.get(run.experiment_id)
            if experiment is not None:
                benchmark_counts[experiment.benchmark_name.value] += 1
            candidate_time = run.completed_at or run.started_at or run.created_at
            if latest_run_at is None or candidate_time > latest_run_at:
                latest_run_at = candidate_time

        total_runs = len(runs)
        failed_runs = status_counts.get(RunStatus.FAILED, 0)
        stats = ExperimentCohortStats(
            cohort_id=cohort_id,
            total_runs=total_runs,
            pending_runs=status_counts.get(RunStatus.PENDING, 0),
            executing_runs=status_counts.get(RunStatus.EXECUTING, 0),
            evaluating_runs=status_counts.get(RunStatus.EVALUATING, 0),
            completed_runs=status_counts.get(RunStatus.COMPLETED, 0),
            failed_runs=failed_runs,
            average_score=(sum(scored_values) / len(scored_values)) if scored_values else None,
            best_score=max(scored_values) if scored_values else None,
            worst_score=min(scored_values) if scored_values else None,
            average_duration_ms=(sum(durations_ms) // len(durations_ms)) if durations_ms else None,
            failure_rate=(failed_runs / total_runs) if total_runs else 0.0,
            stats_json={
                "benchmark_counts": dict(benchmark_counts),
                "latest_run_at": latest_run_at.isoformat() if latest_run_at is not None else None,
            },
            updated_at=utcnow(),
        )
        return queries.experiment_cohort_stats.upsert(stats)

    @staticmethod
    def _score_value(run: Run) -> float | None:
        """Choose the score field used for cohort aggregates."""
        if run.normalized_score is not None:
            return run.normalized_score
        return run.final_score


experiment_cohort_stats_service = ExperimentCohortStatsService()
