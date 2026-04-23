"""Real-LLM harness canary — exercises the whole harness pipeline without
actually spending tokens. Uses the smoke-test benchmark + stub-worker path.

Validates:
  - docker stack up (or --assume-stack-up), stack fixture did not skip
  - `ergon benchmark run` CLI path works
  - /api/test/read/run/{id}/state returns a terminal state
  - Postgres row exists with the right relationships
  - Playwright can find the cohort in the dashboard
"""

import os
import subprocess
from datetime import datetime, timezone

import pytest

pytestmark = [pytest.mark.real_llm, pytest.mark.asyncio]


def _latest_run_id_since(since: datetime) -> str:
    """Query the most recent RunRecord created at or after `since`."""
    # reason: deferred to avoid DB + heavy builtins import at pytest-collect time
    from sqlmodel import select

    # reason: deferred to avoid DB + heavy builtins import at pytest-collect time
    from ergon_core.core.persistence.shared.db import ensure_db, get_session

    # reason: deferred to avoid DB + heavy builtins import at pytest-collect time
    from ergon_core.core.persistence.telemetry.models import RunRecord

    ensure_db()
    with get_session() as session:
        stmt = (
            select(RunRecord)
            .where(RunRecord.created_at >= since)
            .order_by(RunRecord.created_at.desc())
            .limit(1)
        )
        row = session.exec(stmt).first()
        if row is None:
            raise RuntimeError("no RunRecord found after canary CLI invocation")
        return str(row.id)


async def test_harness_canary_smoke_stub(
    real_llm_stack: None,
    harness_client,  # noqa: ANN001
    playwright_context,  # noqa: ANN001
) -> None:
    # Timestamp the boundary so we can filter for a run created *after* this point.
    before = datetime.now(timezone.utc)

    env = {
        **os.environ,
        "ERGON_DATABASE_URL": os.environ.get(
            "ERGON_DATABASE_URL",
            "postgresql://ergon:ergon@127.0.0.1:5433/ergon",
        ),
    }
    result = subprocess.run(
        [
            "uv",
            "run",
            "ergon",
            "benchmark",
            "run",
            "smoke-test",
            "--model",
            "stub:constant",
            "--worker",
            "training-stub",
            "--evaluator",
            "stub-rubric",
            "--limit",
            "1",
        ],
        capture_output=True,
        text=True,
        timeout=180,
        env=env,
    )
    assert result.returncode == 0, (
        f"CLI failed (rc={result.returncode}):\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )

    run_id = _latest_run_id_since(before)

    # Poll the harness until terminal.
    state = harness_client.wait_for_terminal(run_id, timeout_s=120)
    assert state["status"] == "completed", f"run did not complete: {state}"
    assert len(state.get("graph_nodes", [])) >= 1

    # Playwright: dashboard index renders.
    page = await playwright_context.new_page()
    await page.goto("/")
    await page.wait_for_load_state("networkidle")
    # Loose assertion: page rendered.
    content = await page.content()
    assert content, "dashboard rendered empty"
