"""E2E tests: canonical demo runs through the full CLI pipeline.

Two per-dataset demos live here, both running a real manager+worker DAG
against a real sandbox with a real LLM.  They are the load-bearing CI
gates for the stub-consolidation RFC.

``TestResearchRubricsDemo``::

    ergon benchmark run researchrubrics --limit 1 \\
        --worker researchrubrics-manager --evaluator stub-rubric

Exercises ``add_subtask`` delegation, ``SandboxResourcePublisher``
host/sandbox I/O, and the ``StubCriterion`` bash canary.

``TestMiniF2FDemo``::

    ergon benchmark run minif2f-smoke --limit 1 \\
        --worker minif2f-manager --evaluator minif2f-rubric

Same manager→prover delegation pattern, but the "canary" is a real
Lean 4 compile: ``ProofVerificationCriterion`` reads the worker's
``final_solution.lean`` and runs ``lake env lean src/verify.lean``.
Scores 1.0 iff the Lean kernel accepts the proof.

Requires:
  - docker-compose.ci.yml running (postgres + inngest + api)
  - ERGON_DATABASE_URL set to the Postgres instance
  - OPENAI_API_KEY set (managers + sub-agents are real LLM agents).
    CI populates this from the ``OPENROUTER_API_KEY`` secret and sets
    ``OPENAI_BASE_URL=https://openrouter.ai/api/v1`` +
    ``ERGON_MODEL=openai:openai/gpt-4o-mini`` to route through a cheap,
    reliable tool-calling model.  See
    ``.github/workflows/e2e-benchmarks.yml``.
  - E2B sandbox available (docker-compose local, or E2B_API_KEY);
    minif2f also requires the ``ergon-minif2f-v1`` Lean 4 template.

Locally, running without ``OPENAI_API_KEY`` cleanly skips these tests.
Under ``CI=true`` a missing key is a **hard failure** — a silently
skipped job is worse than a red one because it can masquerade as
coverage (this previously let a no-op "green" demo ship to main).
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
    """Require a real LLM key to exercise the manager/researcher ReAct loop.

    Locally (no ``CI`` env var) we skip so developers without keys can
    still run the fast test suite.  Under ``CI=true`` a missing key is
    a hard failure: we previously shipped a green-badge no-op because
    the CI secret was silently empty and the skip hid it.  Never again.
    """
    if os.environ.get("OPENAI_API_KEY"):
        return
    if os.environ.get("CI", "").lower() in {"1", "true", "yes"}:
        pytest.fail(
            "OPENAI_API_KEY not set in CI. The workflow wires the "
            "OPENROUTER_API_KEY secret through as OPENAI_API_KEY (see "
            ".github/workflows/e2e-benchmarks.yml). A missing key here "
            "means the secret is not configured on the repo — fix it in "
            "GitHub → Settings → Secrets rather than letting the job skip."
        )
    pytest.skip("OPENAI_API_KEY not set — skipping real-LLM demo run (local).")


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


MINIF2F_SLUG = "minif2f-smoke"
MINIF2F_WORKER = "minif2f-manager"
MINIF2F_EVALUATOR = "minif2f-rubric"
# Lean sandbox boot + manager→prover spawn + prover proof + manager
# proof rewrite + Lean compile all take longer than the researchrubrics
# demo; allow 15 min of headroom before giving up on the CLI run.
MINIF2F_TIMEOUT = 900


def _minif2f_run(cohort: str):
    return run_benchmark(
        MINIF2F_SLUG,
        worker=MINIF2F_WORKER,
        evaluator=MINIF2F_EVALUATOR,
        cohort=cohort,
        limit=1,
        timeout=MINIF2F_TIMEOUT,
    )


class TestMiniF2FDemo:
    """Canonical minif2f demo: manager+prover delegation into a real Lean
    sandbox, scored by ``minif2f-rubric`` (``ProofVerificationCriterion``)
    which compiles the agent's ``final_solution.lean`` with the Lean
    kernel.  Score 1.0 iff the kernel accepts the proof."""

    def test_run_completes(self):
        result = _minif2f_run("ci-minif2f-demo")
        assert result.returncode == 0, (
            f"CLI exited {result.returncode}:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "Status:     completed" in result.stdout

    def test_executions_complete(self):
        """Manager + ≥1 spawned prover executions all reach terminal-completed."""
        _minif2f_run("ci-minif2f-exec")

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
                f"Expected ≥2 executions (manager + ≥1 spawned prover), got {len(executions)}"
            )

            for ex in executions:
                assert ex.status == TaskExecutionStatus.COMPLETED, (
                    f"Execution {ex.id} status={ex.status}, expected completed"
                )
                assert ex.completed_at is not None

    def test_proof_verification_scores_one(self):
        """``minif2f-rubric`` must return score=1.0 on the trivial smoke theorem.

        This is the load-bearing Lean assertion: if the manager wrote a
        valid proof to ``/workspace/final_output/final_solution.lean``,
        ``ProofVerificationCriterion`` reads that artifact, writes it into
        the sandbox at ``src/verify.lean``, and runs the Lean 4 compiler.
        Exit code 0 ⇒ verified ⇒ score 1.0.  Any regression in worker
        output wiring, sandbox reachability, or the Lean toolchain flips
        this to 0 with a specific feedback reason.
        """
        _minif2f_run("ci-minif2f-score")

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
                    f"Expected minif2f-rubric score=1.0 (Lean kernel accepts proof), "
                    f"got {ev.score}. Feedback: {ev.feedback}"
                )
                assert ev.passed is True
