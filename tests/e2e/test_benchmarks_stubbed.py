"""E2E tests: canonical demo runs through the full CLI pipeline.

Two per-dataset demos live here, both running a real manager+worker DAG
against a real sandbox with a real LLM.  They are the load-bearing CI
gates for the stub-consolidation RFC.

``TestResearchRubricsDemo``::

    ergon benchmark run researchrubrics-vanilla --limit 1 \\
        --worker researchrubrics-manager --evaluator stub-rubric

Exercises ``add_subtask`` delegation, ``SandboxResourcePublisher``
host/sandbox I/O, and the ``StubCriterion`` bash canary.

We use the *vanilla* slug (not the ablated one) specifically because
the ablated loader's fallback path calls ``HfApi().whoami()`` to build
a per-user dataset slug, which requires an HF token the CI runner
doesn't have (see run 24578046124 for the concrete
``LocalTokenNotFoundError``).  Vanilla hardcodes
``ScaleAI/researchrubrics`` — a public dataset that needs no auth.
Managers, subtask-spawn wiring, and the stub evaluator chain are all
identical between the two variants, so the demo coverage is unchanged.

``TestMiniF2FDemo``::

    ergon benchmark run minif2f-smoke --limit 1 \\
        --worker minif2f-manager --evaluator minif2f-rubric

Same manager→prover delegation pattern, but the "canary" is a real
Lean 4 compile: ``ProofVerificationCriterion`` reads the worker's
``final_solution.lean`` and runs ``lake env lean src/verify.lean``.
Scores 1.0 iff the Lean kernel accepts the proof.

Each suite runs the benchmark **once per test class** via a
module-scoped fixture (``_researchrubrics_run`` / ``_minif2f_run``),
and every test in that class asserts a different facet (CLI exit,
execution rows, evaluation score, summary payload, cohort row) against
the shared run.  Earlier versions of this file re-ran ``_demo_run()``
inside every test — that's 5× the LLM credits, 5× the sandbox boot
time, and enough variance that a single slow run could push a single
job past the 20-minute timeout (see run 24580074997).  One run, many
assertions keeps coverage identical and the job budget honest.

Requires:
  - docker-compose.ci.yml running (postgres + inngest + api)
  - ERGON_DATABASE_URL set to the Postgres instance
  - An LLM provider key — either ``OPENROUTER_API_KEY`` (the CI
    posture, routed via the ``openrouter:`` model-target prefix and
    pydantic-ai's ``OpenRouterProvider``) or ``OPENAI_API_KEY`` for
    direct OpenAI.  CI sets ``ERGON_MODEL=openrouter:openai/gpt-4o-mini``
    — a cheap, reliable tool-calling model — and wires the key into
    both the runner and the api container.  See
    ``.github/workflows/e2e-benchmarks.yml`` +
    ``ergon_builtins/models/openrouter_backend.py``.
  - E2B sandbox available (docker-compose local, or E2B_API_KEY);
    minif2f also requires the ``ergon-minif2f-v1`` Lean 4 template.

Locally, running without any provider key cleanly skips these tests.
Under ``CI=true`` a missing key is a **hard failure** — a silently
skipped job is worse than a red one because it can masquerade as
coverage (this previously let a no-op "green" demo ship to main).
"""

import os
import subprocess
import uuid
from dataclasses import dataclass

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

# Vanilla, not ablated: ablated's loader calls ``HfApi().whoami()`` in
# its dataset-name fallback, which needs an HF token the CI runner has
# no reason to hold.  Vanilla points at the public
# ``ScaleAI/researchrubrics`` and needs no auth.  See the module
# docstring for context.
DEMO_SLUG = "researchrubrics-vanilla"
DEMO_WORKER = "researchrubrics-manager"
DEMO_EVALUATOR = "stub-rubric"
DEMO_TIMEOUT = 600  # manager → plan → spawn → researcher → report; allow headroom


def _get_session() -> Session:
    return Session(get_engine())


@dataclass
class DemoRun:
    """Captured output of a single ``ergon benchmark run`` invocation.

    Tests assert facets (CLI exit, execution rows, evaluation score, ...)
    against one of these.  Pinning ``run_id`` at fixture time means each
    test queries *exactly* the run this fixture produced — no racing on
    ``ORDER BY created_at DESC LIMIT 1`` if fixtures from other suites
    happen to interleave.
    """

    process: subprocess.CompletedProcess
    cohort: str
    run_id: str | None


def _capture_latest_run_id() -> str | None:
    """Return the most-recent ``RunRecord.id``, or ``None`` if table is empty.

    Called immediately after a CLI run so "most recent" unambiguously
    identifies the run we just kicked off.  Returned as a string so the
    dataclass stays JSON-serialisable for diagnostic dumps.
    """
    with _get_session() as session:
        latest = session.exec(
            select(RunRecord)
            .order_by(RunRecord.created_at.desc())  # type: ignore[union-attr]
            .limit(1)
        ).first()
        return str(latest.id) if latest else None


@pytest.fixture(scope="session", autouse=True)
def _require_api_keys():
    """Require a real LLM key to exercise the manager/researcher ReAct loop.

    Accepts either ``OPENROUTER_API_KEY`` (the current CI posture — see
    ``ergon_builtins/models/openrouter_backend.py``) or ``OPENAI_API_KEY``
    (direct OpenAI, for local development without an OpenRouter account).
    Whichever is present, pydantic-ai's provider resolution reads it
    automatically when the matching model-target prefix (``openrouter:``
    or ``openai:``) is dispatched.

    Session-scoped so the check fires **before** the module-scoped demo
    fixtures set up.  If it were function-scoped, pytest would spin up
    the module fixture (i.e. run a full benchmark) *before* running
    this check, so a missing key would burn an E2B sandbox + LLM credit
    before skipping.  Session scope guarantees the skip/fail happens
    first.

    Locally (no ``CI`` env var) we skip so developers without keys can
    still run the fast test suite.  Under ``CI=true`` a missing key is
    a hard failure: we previously shipped a green-badge no-op because
    the CI secret was silently empty and the skip hid it.  Never again.
    """
    if os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENAI_API_KEY"):
        return
    if os.environ.get("CI", "").lower() in {"1", "true", "yes"}:
        pytest.fail(
            "No LLM provider key set in CI. The workflow passes the "
            "OPENROUTER_API_KEY secret through to both the runner and "
            "the api container (see .github/workflows/e2e-benchmarks.yml "
            "and docker-compose.ci.yml).  A missing key here means the "
            "secret is not configured on the repo — fix it in GitHub → "
            "Settings → Secrets rather than letting the job skip."
        )
    pytest.skip(
        "No LLM provider key set (OPENROUTER_API_KEY or OPENAI_API_KEY) — "
        "skipping real-LLM demo run (local)."
    )


@pytest.fixture(scope="module")
def _researchrubrics_run() -> DemoRun:
    """Run the researchrubrics demo **once** per module; yield to all tests.

    Each test in ``TestResearchRubricsDemo`` asserts a different facet
    of the same pipeline execution.  Running the full CLI → Inngest →
    worker → sandbox cycle once and sharing the result:

    - Cuts LLM + E2B spend by 5× versus the previous per-test reruns.
    - Keeps the researchrubrics job's wall-clock well under its
      20-minute ceiling (previously we were hitting the per-test 600s
      safety timeout with zero margin; see run 24580074997).
    - Preserves "one assertion per test" error localisation — each
      test still points at exactly one failure mode.

    Cohort name is uuid-suffixed so ``test_cohort_created`` can assert
    a unique row was written without collisions across CI runs reusing
    the same Postgres volume.
    """
    cohort = f"ci-researchrubrics-{uuid.uuid4().hex[:8]}"
    result = run_benchmark(
        DEMO_SLUG,
        worker=DEMO_WORKER,
        evaluator=DEMO_EVALUATOR,
        cohort=cohort,
        limit=1,
        timeout=DEMO_TIMEOUT,
    )
    return DemoRun(process=result, cohort=cohort, run_id=_capture_latest_run_id())


class TestResearchRubricsDemo:
    """Canonical demo: manager+researcher delegation into a real sandbox,
    evaluated by ``stub-rubric`` which asserts the full pipeline works."""

    def test_run_completes(self, _researchrubrics_run: DemoRun):
        result = _researchrubrics_run.process
        assert result.returncode == 0, (
            f"CLI exited {result.returncode}:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "Status:     completed" in result.stdout

    def test_executions_complete(self, _researchrubrics_run: DemoRun):
        """Every execution (manager + spawned researcher subtasks) completes."""
        run_id = _researchrubrics_run.run_id
        assert run_id is not None, "fixture failed to capture a RunRecord"

        with _get_session() as session:
            executions = list(
                session.exec(
                    select(RunTaskExecution).where(RunTaskExecution.run_id == run_id)
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

    def test_stub_criterion_scores_one(self, _researchrubrics_run: DemoRun):
        """``stub-rubric`` must return score=1.0 on a real pipeline run.

        This is the load-bearing assertion of the whole consolidation:
        if the evaluator, resource store, and sandbox runtime are all
        wired up correctly, ``StubCriterion`` sees resources it can read
        both host-side and sandbox-side and the canary succeeds.  Any
        regression in that chain flips this to 0.0 with a specific
        feedback reason.
        """
        run_id = _researchrubrics_run.run_id
        assert run_id is not None, "fixture failed to capture a RunRecord"

        with _get_session() as session:
            run = session.exec(select(RunRecord).where(RunRecord.id == run_id)).first()
            assert run is not None
            assert run.status == RunStatus.COMPLETED

            evaluations = list(
                session.exec(
                    select(RunTaskEvaluation).where(RunTaskEvaluation.run_id == run_id)
                ).all()
            )
            assert len(evaluations) > 0, "Expected at least one evaluation"
            for ev in evaluations:
                assert ev.score == 1.0, (
                    f"Expected stub-rubric score=1.0 (resources + sandbox canary), "
                    f"got {ev.score}. Feedback: {ev.feedback}"
                )
                assert ev.passed is True

    def test_summary_json_populated(self, _researchrubrics_run: DemoRun):
        run_id = _researchrubrics_run.run_id
        assert run_id is not None, "fixture failed to capture a RunRecord"

        with _get_session() as session:
            run = session.exec(select(RunRecord).where(RunRecord.id == run_id)).first()
            assert run is not None
            summary = run.parsed_summary()
            assert "final_score" in summary
            assert "normalized_score" in summary
            assert "evaluators_count" in summary

    def test_cohort_created(self, _researchrubrics_run: DemoRun):
        """Cohort row exists after a demo run."""
        cohort_name = _researchrubrics_run.cohort

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


@pytest.fixture(scope="module")
def _minif2f_run() -> DemoRun:
    """Run the minif2f smoke demo **once** per module; yield to all tests.

    Same rationale as ``_researchrubrics_run`` — one full Lean pipeline
    execution is shared across all assertions in ``TestMiniF2FDemo``.
    Lean sandbox boot alone is ~2 minutes, so deduplicating the runs is
    even more important here; the previous per-test variant was
    reliably blowing the 25-minute job cap.
    """
    cohort = f"ci-minif2f-{uuid.uuid4().hex[:8]}"
    result = run_benchmark(
        MINIF2F_SLUG,
        worker=MINIF2F_WORKER,
        evaluator=MINIF2F_EVALUATOR,
        cohort=cohort,
        limit=1,
        timeout=MINIF2F_TIMEOUT,
    )
    return DemoRun(process=result, cohort=cohort, run_id=_capture_latest_run_id())


class TestMiniF2FDemo:
    """Canonical minif2f demo: manager+prover delegation into a real Lean
    sandbox, scored by ``minif2f-rubric`` (``ProofVerificationCriterion``)
    which compiles the agent's ``final_solution.lean`` with the Lean
    kernel.  Score 1.0 iff the kernel accepts the proof."""

    def test_run_completes(self, _minif2f_run: DemoRun):
        result = _minif2f_run.process
        assert result.returncode == 0, (
            f"CLI exited {result.returncode}:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "Status:     completed" in result.stdout

    def test_executions_complete(self, _minif2f_run: DemoRun):
        """Manager + ≥1 spawned prover executions all reach terminal-completed."""
        run_id = _minif2f_run.run_id
        assert run_id is not None, "fixture failed to capture a RunRecord"

        with _get_session() as session:
            executions = list(
                session.exec(
                    select(RunTaskExecution).where(RunTaskExecution.run_id == run_id)
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

    def test_proof_verification_scores_one(self, _minif2f_run: DemoRun):
        """``minif2f-rubric`` must return score=1.0 on the trivial smoke theorem.

        This is the load-bearing Lean assertion: if the manager wrote a
        valid proof to ``/workspace/final_output/final_solution.lean``,
        ``ProofVerificationCriterion`` reads that artifact, writes it into
        the sandbox at ``src/verify.lean``, and runs the Lean 4 compiler.
        Exit code 0 ⇒ verified ⇒ score 1.0.  Any regression in worker
        output wiring, sandbox reachability, or the Lean toolchain flips
        this to 0 with a specific feedback reason.
        """
        run_id = _minif2f_run.run_id
        assert run_id is not None, "fixture failed to capture a RunRecord"

        with _get_session() as session:
            run = session.exec(select(RunRecord).where(RunRecord.id == run_id)).first()
            assert run is not None
            assert run.status == RunStatus.COMPLETED

            evaluations = list(
                session.exec(
                    select(RunTaskEvaluation).where(RunTaskEvaluation.run_id == run_id)
                ).all()
            )
            assert len(evaluations) > 0, "Expected at least one evaluation"
            for ev in evaluations:
                assert ev.score == 1.0, (
                    f"Expected minif2f-rubric score=1.0 (Lean kernel accepts proof), "
                    f"got {ev.score}. Feedback: {ev.feedback}"
                )
                assert ev.passed is True
