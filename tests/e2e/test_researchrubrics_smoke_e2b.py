"""Real-E2B smoke test for the researchrubrics pipeline.

Runs the ``researchrubrics-smoke`` benchmark end-to-end with a real E2B
sandbox.  The stub worker writes a deterministic markdown report; the stub
criterion checks the report exists as a RunResource with the expected
section headers and valid content hash.

Gated on ``E2B_API_KEY`` -- skipped in fast-test runs.  Picked up by the
``e2e-sandbox`` job in ``.github/workflows/e2e-benchmarks.yml`` on
``feature/*`` branches (same mechanism as the existing minif2f / smoke-test
E2B tests in ``TestE2BSandboxBenchmarks``).

Requires:
  - docker-compose.ci.yml running (postgres + inngest + api)
  - ERGON_DATABASE_URL set to the Postgres instance
  - E2B_API_KEY set
"""

import os

import pytest
from ergon_core.core.persistence.shared.db import get_engine
from ergon_core.core.persistence.shared.enums import RunStatus
from ergon_core.core.persistence.telemetry.models import (
    RunRecord,
    RunResource,
    RunResourceKind,
    RunTaskEvaluation,
)
from sqlmodel import Session, select

from tests.e2e.conftest import run_benchmark


def _get_session() -> Session:
    return Session(get_engine())


class TestResearchRubricsSmokeE2B:
    """Real-E2B smoke test: stub worker -> publisher -> criterion."""

    @pytest.fixture(autouse=True)
    def _require_e2b(self):
        if not os.environ.get("E2B_API_KEY"):
            pytest.skip("E2B_API_KEY not set -- skipping real-E2B smoke test")

    def test_stub_worker_writes_report_and_criterion_passes(self):
        """Stub worker writes report.md -> RunResource row -> criterion passes."""
        result = run_benchmark(
            "researchrubrics-smoke",
            worker="researchrubrics-stub",
            evaluator="researchrubrics-smoke-rubric",
            cohort="ci-researchrubrics-smoke",
        )
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

            # Verify RunResource(kind=REPORT) row exists.
            resources = list(
                session.exec(
                    select(RunResource).where(
                        RunResource.run_id == latest_run.id,
                    )
                ).all()
            )
            report_rows = [r for r in resources if r.kind == RunResourceKind.REPORT.value]
            assert len(report_rows) >= 1, (
                f"Expected at least one REPORT resource, "
                f"found {len(report_rows)} out of {len(resources)} total"
            )

            report = report_rows[0]
            assert report.content_hash is not None
            assert report.size_bytes > 0

            # Verify the blob file exists and its hash matches.
            import hashlib
            from pathlib import Path

            blob = Path(report.file_path)
            assert blob.exists(), f"Blob file missing at {report.file_path}"
            actual_hash = hashlib.sha256(blob.read_bytes()).hexdigest()
            assert actual_hash == report.content_hash, (
                f"Hash mismatch: row={report.content_hash}, blob={actual_hash}"
            )

            # Verify the blob contains expected sections.
            content = blob.read_text(encoding="utf-8")
            assert "# Findings" in content
            assert "## Sources" in content

            # Verify evaluations passed.
            evaluations = list(
                session.exec(
                    select(RunTaskEvaluation).where(
                        RunTaskEvaluation.run_id == latest_run.id,
                    )
                ).all()
            )
            assert len(evaluations) >= 1
            for ev in evaluations:
                assert ev.score == 1.0, (
                    f"Expected score=1.0, got {ev.score}. Feedback: {ev.feedback}"
                )
                assert ev.passed is True
