"""E2E tests: canonical demo run through the full CLI pipeline.

After the stub-consolidation RFC the demo command is a single line:

    ergon benchmark run researchrubrics --limit 1 \\
        --worker researchrubrics-manager --evaluator stub-rubric

It exercises every stage that used to be covered by three separate
"smoke" benchmarks:

* **Delegation path**: ``researchrubrics-manager`` spawns
  ``researchrubrics-researcher`` subtasks via ``add_subtask``.  That
  confirms dynamic DAG expansion + sub-worker resolution work.
* **Sandbox I/O**: the researcher writes a real report file under
  ``/workspace/final_output/report.md`` and ``SandboxResourcePublisher``
  syncs it to a ``RunResource``.
* **Evaluation actually runs**: the new ``StubCriterion`` reads back
  the RunResource, probes the sandbox for each blob, and fires a
  ``echo $((1+1))`` canary.  ``score == 1.0`` iff all three checks
  pass end-to-end.

Requires:
  - docker-compose.ci.yml running (postgres + inngest + api)
  - ERGON_DATABASE_URL set to the Postgres instance
  - OPENAI_API_KEY set (manager + researcher are real LLM agents)
  - E2B sandbox available (docker-compose local, or E2B_API_KEY)
"""

import os

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

DEMO_SLUG = "researchrubrics"
DEMO_WORKER = "researchrubrics-manager"
DEMO_EVALUATOR = "stub-rubric"
DEMO_TIMEOUT = 600  # manager → plan → spawn → researcher → report; allow headroom


def _get_session() -> Session:
    return Session(get_engine())


def _demo_run(cohort: str):
    return run_benchmark(
        DEMO_SLUG,
        worker=DEMO_WORKER,
        evaluator=DEMO_EVALUATOR,
        cohort=cohort,
        limit=1,
        timeout=DEMO_TIMEOUT,
    )


@pytest.fixture(autouse=True)
def _require_api_keys():
    if not os.environ.get("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY not set — skipping researchrubrics demo run")


class TestResearchRubricsDemo:
    """Canonical demo: manager+researcher delegation into a real sandbox,
    evaluated by ``stub-rubric`` which asserts the full pipeline works."""

    def test_run_completes(self):
        result = _demo_run("ci-researchrubrics-demo")
        assert result.returncode == 0, (
            f"CLI exited {result.returncode}:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "Status:     completed" in result.stdout

    def test_executions_complete(self):
        """Every execution (manager + spawned researcher subtasks) completes."""
        _demo_run("ci-researchrubrics-exec")

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
            assert len(executions) >= 2, (
                f"Expected ≥2 executions (manager + ≥1 spawned researcher), got {len(executions)}"
            )

            for ex in executions:
                assert ex.status == TaskExecutionStatus.COMPLETED, (
                    f"Execution {ex.id} status={ex.status}, expected completed"
                )
                assert ex.completed_at is not None

    def test_stub_criterion_scores_one(self):
        """``stub-rubric`` must return score=1.0 on a real pipeline run.

        This is the load-bearing assertion of the whole consolidation:
        if the evaluator, resource store, and sandbox runtime are all
        wired up correctly, ``StubCriterion`` sees resources it can read
        both host-side and sandbox-side and the canary succeeds.  Any
        regression in that chain flips this to 0.0 with a specific
        feedback reason.
        """
        _demo_run("ci-researchrubrics-score")

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
                assert ev.score == 1.0, (
                    f"Expected stub-rubric score=1.0 (resources + sandbox canary), "
                    f"got {ev.score}. Feedback: {ev.feedback}"
                )
                assert ev.passed is True

    def test_summary_json_populated(self):
        _demo_run("ci-researchrubrics-summary")

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
        """Cohort row exists after a demo run."""
        cohort_name = "ci-cohort-check"
        _demo_run(cohort_name)

        with _get_session() as session:
            cohort = session.exec(
                select(ExperimentCohort).where(ExperimentCohort.name == cohort_name)
            ).first()
            assert cohort is not None, f"Cohort {cohort_name!r} should exist"
