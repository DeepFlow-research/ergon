"""Real-LLM rollout harness for the ``researchrubrics`` benchmark.

This test is a **trigger**, not an assertion suite.  It runs a real
``ergon benchmark run researchrubrics`` end-to-end against a real LLM
(Sonnet 4.6 via OpenRouter by default) and dumps an exhaustive
rollout artifact — every persistence table, dashboard screenshots,
and a stitched ``report.md`` — to
``tests/real_llm/.rollouts/<timestamp>-<run_id>/``.

A reviewing agent (or human) then opens ``report.md`` and reasons
about whether the agent succeeded, and what to iterate on in the
model or simulator.

The single assertion is that the benchmark reached a terminal status
(``completed`` / ``failed`` / ``cancelled``).  ``failed`` is still a
successful rollout from the harness's perspective — it is data.

Gated by:
- ``ERGON_REAL_LLM=1`` (via the ``real_llm`` pytest marker, enforced
  in ``tests/real_llm/conftest.py``).
- ``OPENROUTER_API_KEY`` (via the session-level budget fixture).
- ``EXA_API_KEY`` + ``E2B_API_KEY`` (this module's ``_require_keys``
  autouse fixture).
"""

import os
import subprocess
import time
from datetime import datetime, timezone
from uuid import UUID

import pytest
from sqlmodel import select

from ergon_core.core.persistence.shared.db import ensure_db, get_session
from ergon_core.core.persistence.telemetry.models import (
    RunRecord,
    RunResource,
    RunTaskEvaluation,
)
from ergon_core.core.providers.generation.openrouter_budget import OpenRouterBudget
from ergon_core.core.settings import settings

from tests.real_llm.rollout import (
    capture_dashboard,
    dump_rollout,
    rollout_dir,
    write_manifest,
    write_report,
)
from tests.real_llm.rollout import _fingerprint as fingerprint

pytestmark = [pytest.mark.real_llm, pytest.mark.asyncio]

# Default to Sonnet 4.6 via OpenRouter.  Override with ERGON_REAL_LLM_MODEL
# to roll out against a different model without editing the test.
_DEFAULT_MODEL = "openrouter:anthropic/claude-sonnet-4.6"

# Wall-clock caps.  Real-LLM + real-sandbox rollouts are slow; keep
# these generous enough to absorb E2B startup + Exa retries but bounded
# so a wedged run surfaces instead of hanging a session.
_CLI_TIMEOUT_SECONDS = 900
_HARNESS_POLL_TIMEOUT_SECONDS = 900
_POST_TERMINAL_ARTIFACT_TIMEOUT_SECONDS = 300


@pytest.fixture(autouse=True)
def _require_keys() -> None:
    """Skip unless every settings key this rollout touches is populated.

    Provider-specific keys are selected from ``ERGON_REAL_LLM_MODEL`` so
    the rollout harness can run against OpenAI on machines that do not
    have OpenRouter configured.
    """
    model = os.environ.get("ERGON_REAL_LLM_MODEL", _DEFAULT_MODEL)
    provider_key = model.split(":", 1)[0]
    provider_settings = {
        "openai": "openai_api_key",
        "openrouter": "openrouter_api_key",
    }
    required = ["exa_api_key", "e2b_api_key"]
    if provider_key in provider_settings:
        required.append(provider_settings[provider_key])

    missing = settings.missing_values(
        required,
    )
    if missing:
        pytest.skip(
            f"researchrubrics rollout requires {missing} — set them in .env "
            "or environment before invoking this tier."
        )


def _latest_run_id_since(since: datetime) -> UUID:
    """Return the most recent RunRecord.id created at or after ``since``."""
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
            raise RuntimeError(
                "no RunRecord created since the harness started — "
                "did the CLI subprocess actually dispatch a run?"
            )
        return row.id


def _wait_for_post_terminal_artifacts(run_id: UUID) -> None:
    """Let async resource/evaluation rows land before dumping artifacts."""
    deadline = time.monotonic() + _POST_TERMINAL_ARTIFACT_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        with get_session() as session:
            resources = len(
                list(session.exec(select(RunResource).where(RunResource.run_id == run_id)).all())
            )
            evaluations = len(
                list(
                    session.exec(
                        select(RunTaskEvaluation).where(RunTaskEvaluation.run_id == run_id)
                    ).all()
                )
            )
        if resources > 0 and evaluations > 0:
            return
        time.sleep(2)


async def test_researchrubrics_rollout(
    real_llm_stack: None,  # session fixture: stack up
    harness_client,  # noqa: ANN001  # poll /api/test/read/run/{id}/state
    playwright_context,  # noqa: ANN001  # dashboard screenshots
    openrouter_budget: OpenRouterBudget | None,
) -> None:
    """End-to-end researchrubrics rollout against a real LLM.

    The rollout is the product: this test produces a snapshot the next
    agent session reads back.  We do not assert on scores, tool counts,
    node shapes, or UI content — only that the run reached a terminal
    state inside the time budget.
    """
    model = os.environ.get("ERGON_REAL_LLM_MODEL", _DEFAULT_MODEL)
    benchmark = "researchrubrics"
    worker = "researchrubrics-researcher"
    evaluator = "research-rubric"

    budget_before = (
        await openrouter_budget.remaining_usd() if openrouter_budget is not None else None
    )
    started_at = datetime.now(timezone.utc)

    cli_proc = subprocess.run(
        [
            "uv",
            "run",
            "ergon",
            "benchmark",
            "run",
            benchmark,
            "--worker",
            worker,
            "--evaluator",
            evaluator,
            "--model",
            model,
            "--limit",
            "1",
        ],
        timeout=_CLI_TIMEOUT_SECONDS,
        capture_output=True,
        text=True,
        check=False,
    )

    run_id = _latest_run_id_since(started_at)
    terminal_state = harness_client.wait_for_terminal(
        run_id,
        timeout_s=_HARNESS_POLL_TIMEOUT_SECONDS,
    )
    _wait_for_post_terminal_artifacts(run_id)

    out_dir = rollout_dir(run_id)

    # Persist CLI stdout/stderr up front so a crashed DB dump still
    # leaves breadcrumbs for the reviewing agent.
    (out_dir / "cli_stdout.txt").write_text(cli_proc.stdout or "")
    (out_dir / "cli_stderr.txt").write_text(cli_proc.stderr or "")

    table_counts = dump_rollout(run_id, out_dir)
    screenshots = await capture_dashboard(run_id, playwright_context, out_dir)

    finished_at = datetime.now(timezone.utc)
    budget_after = await openrouter_budget.remaining_usd() if openrouter_budget is not None else None

    manifest_path = write_manifest(
        out_dir,
        run_id=run_id,
        benchmark=benchmark,
        worker=worker,
        evaluator=evaluator,
        model=model,
        cli_returncode=cli_proc.returncode,
        terminal_state=terminal_state,
        started_at=started_at,
        finished_at=finished_at,
        table_row_counts=table_counts,
        screenshots=screenshots,
        key_fingerprints={
            "openrouter_api_key": fingerprint(settings.openrouter_api_key),
            "exa_api_key": fingerprint(settings.exa_api_key),
            "e2b_api_key": fingerprint(settings.e2b_api_key),
        },
        budget_snapshot=(
            {
                "remaining_usd_before": budget_before,
                "remaining_usd_after": budget_after,
                "spent_usd": budget_before - budget_after,
            }
            if budget_before is not None and budget_after is not None
            else None
        ),
    )
    write_report(out_dir, manifest_path)

    # The single assertion. ``failed`` and ``cancelled`` are still
    # successful rollouts — the artifact is the product.
    assert terminal_state["status"] in {"completed", "failed", "cancelled"}, (
        f"run {run_id} did not reach a terminal status within "
        f"{_HARNESS_POLL_TIMEOUT_SECONDS}s — see {out_dir}"
    )
