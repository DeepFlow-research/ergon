"""E2E tests: run each benchmark via the CLI with stubbed components.

Exercises the full Inngest pipeline (sandbox-setup -> worker-execute ->
persist-outputs -> evaluate -> finalize) and asserts correct DB state.

Requires:
  - docker-compose.ci.yml running (postgres + inngest + api)
  - ERGON_DATABASE_URL set to the Postgres instance
  - E2B_API_KEY set for smoke-test-worker/smoke-test-rubric tests
"""

import pytest
from ergon_core.core.persistence.shared.db import get_engine
from ergon_core.core.persistence.shared.enums import RunStatus, TaskExecutionStatus
from ergon_core.core.persistence.telemetry.models import (
    ExperimentCohort,
    RunRecord,
    RunTaskEvaluation,
    RunTaskExecution,
)
from sqlmodel import Session, select

from tests.e2e.conftest import run_benchmark

STUB_CONFIGS = [
    pytest.param(
        "smoke-test",
        "stub-worker",
        "stub-rubric",
        "ci-stub",
        id="smoke-test/stub/stub",
    ),
    pytest.param(
        "minif2f",
        "stub-worker",
        "stub-rubric",
        "ci-stub",
        id="minif2f/stub/stub",
    ),
]

E2B_CONFIGS = [
    pytest.param(
        "smoke-test",
        "smoke-test-worker",
        "smoke-test-rubric",
        "ci-e2b",
        id="smoke-test/e2b-worker/sandbox-rubric",
    ),
]


def _get_session() -> Session:
    return Session(get_engine())


class TestStubbedBenchmarks:
    """Benchmarks with stub-worker + stub-rubric — no external API keys needed."""

    @pytest.mark.parametrize("slug,worker,evaluator,cohort", STUB_CONFIGS)
    def test_run_completes(self, slug, worker, evaluator, cohort):
        result = run_benchmark(slug, worker=worker, evaluator=evaluator, cohort=cohort)
        assert result.returncode == 0, (
            f"CLI exited {result.returncode}:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "Status:     completed" in result.stdout

    @pytest.mark.parametrize("slug,worker,evaluator,cohort", STUB_CONFIGS)
    def test_single_execution_per_task(self, slug, worker, evaluator, cohort):
        """Each task should have exactly one execution record."""
        run_benchmark(slug, worker=worker, evaluator=evaluator, cohort=cohort)

        with _get_session() as session:
            latest_run = session.exec(
                select(RunRecord)
                .order_by(RunRecord.created_at.desc())  # type: ignore[union-attr]
                .limit(1)
            ).first()
            assert latest_run is not None

            executions = list(
                session.exec(
                    select(RunTaskExecution).where(RunTaskExecution.run_id == latest_run.id)
                ).all()
            )

            for ex in executions:
                assert ex.status == TaskExecutionStatus.COMPLETED, (
                    f"Execution {ex.id} status={ex.status}, expected completed"
                )
                assert ex.completed_at is not None

    @pytest.mark.parametrize("slug,worker,evaluator,cohort", STUB_CONFIGS)
    def test_evaluations_exist(self, slug, worker, evaluator, cohort):
        """Each task should have evaluation records with scores."""
        run_benchmark(slug, worker=worker, evaluator=evaluator, cohort=cohort)

        with _get_session() as session:
            latest_run = session.exec(
                select(RunRecord)
                .order_by(RunRecord.created_at.desc())  # type: ignore[union-attr]
                .limit(1)
            ).first()
            assert latest_run is not None
            assert latest_run.status == RunStatus.COMPLETED

            evaluations = list(
                session.exec(
                    select(RunTaskEvaluation).where(RunTaskEvaluation.run_id == latest_run.id)
                ).all()
            )
            assert len(evaluations) > 0, "Expected at least one evaluation"
            for ev in evaluations:
                assert ev.score is not None

    @pytest.mark.parametrize("slug,worker,evaluator,cohort", STUB_CONFIGS)
    def test_summary_json_populated(self, slug, worker, evaluator, cohort):
        run_benchmark(slug, worker=worker, evaluator=evaluator, cohort=cohort)

        with _get_session() as session:
            latest_run = session.exec(
                select(RunRecord)
                .order_by(RunRecord.created_at.desc())  # type: ignore[union-attr]
                .limit(1)
            ).first()
            assert latest_run is not None
            summary = latest_run.parsed_summary()
            assert "final_score" in summary
            assert "normalized_score" in summary
            assert "evaluators_count" in summary

    def test_cohort_created(self):
        """At least one cohort should exist after running benchmarks."""
        run_benchmark(
            "smoke-test", worker="stub-worker", evaluator="stub-rubric", cohort="ci-cohort-check"
        )

        with _get_session() as session:
            cohort = session.exec(
                select(ExperimentCohort).where(ExperimentCohort.name == "ci-cohort-check")
            ).first()
            assert cohort is not None, "Cohort 'ci-cohort-check' should exist"


class TestE2BSandboxBenchmarks:
    """Benchmarks with real E2B sandbox I/O — requires E2B_API_KEY."""

    @pytest.fixture(autouse=True)
    def _require_e2b(self):
        # Deferred: runtime-only dependency
        import os

        if not os.environ.get("E2B_API_KEY"):
            pytest.skip("E2B_API_KEY not set — skipping sandbox I/O tests")

    @pytest.mark.parametrize("slug,worker,evaluator,cohort", E2B_CONFIGS)
    def test_sandbox_roundtrip(self, slug, worker, evaluator, cohort):
        """Worker writes file -> criterion reads file -> score=1.0."""
        result = run_benchmark(slug, worker=worker, evaluator=evaluator, cohort=cohort)
        assert result.returncode == 0, (
            f"CLI exited {result.returncode}:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )

        with _get_session() as session:
            latest_run = session.exec(
                select(RunRecord)
                .order_by(RunRecord.created_at.desc())  # type: ignore[union-attr]
                .limit(1)
            ).first()
            assert latest_run is not None
            assert latest_run.status == RunStatus.COMPLETED

            evaluations = list(
                session.exec(
                    select(RunTaskEvaluation).where(RunTaskEvaluation.run_id == latest_run.id)
                ).all()
            )
            assert len(evaluations) > 0
            for ev in evaluations:
                assert ev.score == 1.0, (
                    f"Expected score=1.0 (sandbox file found), got {ev.score}. "
                    f"Feedback: {ev.feedback}"
                )
                assert ev.passed is True
