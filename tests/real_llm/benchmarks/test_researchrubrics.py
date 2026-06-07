"""Real-LLM rollout harness for the ``researchrubrics`` environment.

This test is a **trigger**, not an assertion suite.  It submits a real
ResearchRubrics environment through the Python authoring API
(Sonnet 4.6 via OpenRouter by default) and dumps an exhaustive
rollout artifact — every persistence table, dashboard screenshots,
and a stitched ``report.md`` — to
``tests/real_llm/.rollouts/<timestamp>-<sample_id>/``.

A reviewing agent (or human) then opens ``report.md`` and reasons
about whether the agent succeeded, and what to iterate on in the
model or simulator.

The single assertion is that the environment rollout reached a terminal status
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
import json
import time
from datetime import datetime, timezone
from uuid import UUID

import pytest
from ergon_builtins.agents.react.worker import ReActWorker
from ergon_builtins.benchmarks.researchrubrics.dataset import load_researchrubrics_rows
from ergon_builtins.benchmarks.researchrubrics.prompts import RESEARCH_SYSTEM_PROMPT
from ergon_builtins.benchmarks.researchrubrics.rubric import ResearchRubricsRubric
from ergon_builtins.benchmarks.researchrubrics.sandbox import ResearchE2BSandbox
from ergon_builtins.benchmarks.researchrubrics.sample import make_researchrubrics_sample
from ergon_builtins.benchmarks.researchrubrics.toolkit import ResearchRubricsToolkit
from ergon_core.api import Environment, Experiment, RandomSampler
from ergon_core.core.persistence.shared.db import ensure_db, get_session
from ergon_core.core.persistence.telemetry.models import (
    SampleResource,
    SampleTaskEvaluation,
)
from ergon_core.core.shared.settings import settings
from sqlmodel import select

from tests.real_llm.openrouter_budget import OpenRouterBudget
from tests.real_llm.rollout import _fingerprint as fingerprint
from tests.real_llm.rollout import (
    capture_dashboard,
    dump_rollout,
    rollout_dir,
    write_manifest,
    write_report,
)

pytestmark = [pytest.mark.real_llm, pytest.mark.asyncio]

# Default to Sonnet 4.6 via OpenRouter.  Override with ERGON_REAL_LLM_MODEL
# to roll out against a different model without editing the test.
_DEFAULT_MODEL = "openrouter:anthropic/claude-sonnet-4.6"

# Wall-clock caps.  Real-LLM + real-sandbox rollouts are slow; keep
# these generous enough to absorb E2B startup + Exa retries but bounded
# so a wedged run surfaces instead of hanging a session.
_HARNESS_POLL_TIMEOUT_SECONDS = 900
_POST_TERMINAL_ARTIFACT_TIMEOUT_SECONDS = 300


@pytest.fixture(autouse=True)
def _require_keys() -> None:
    """Skip unless every settings key this rollout touches is populated."""
    missing = settings.missing_values(["openrouter_api_key", "exa_api_key", "e2b_api_key"])
    if missing:
        pytest.skip(
            f"researchrubrics rollout requires {missing} — set them in .env "
            "or environment before invoking this tier."
        )


async def _submit_researchrubrics_sample(
    *,
    model: str,
    limit: int,
    max_iterations: int,
) -> tuple[UUID, dict[str, object]]:
    """Submit one ResearchRubrics sample through Python composition."""
    ensure_db()
    with get_session() as session:
        worker = ReActWorker(
            name="research-runner",
            model=model,
            system_prompt=RESEARCH_SYSTEM_PROMPT,
            max_iterations=max_iterations,
            toolkit=ResearchRubricsToolkit(),
        )
        environment = Environment.from_records(
            name="researchrubrics-real-llm",
            records=load_researchrubrics_rows(split="train", limit=limit),
            make_sample=lambda row: make_researchrubrics_sample(
                row,
                environment_name="researchrubrics-real-llm",
                split="train",
                worker=worker,
                evaluators=[ResearchRubricsRubric(name="researchrubrics-rubric")],
                sandbox=ResearchE2BSandbox(),
            ),
        )
        experiment = Experiment(
            name=f"real-llm-researchrubrics-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}",
            environments=[environment],
            metadata={"source": "real-llm-harness"},
        )
        result = await experiment.submit(
            session=session,
            k=1,
            candidate_pool_size=limit,
            sampler=RandomSampler(seed=0),
        )
    if not result.sample_ids:
        raise RuntimeError("ResearchRubrics submission returned no sample_ids")
    return result.sample_ids[0], result.model_dump(mode="json")


def _wait_for_post_terminal_artifacts(sample_id: UUID) -> None:
    """Let async resource/evaluation rows land before dumping artifacts."""
    deadline = time.monotonic() + _POST_TERMINAL_ARTIFACT_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        with get_session() as session:
            resources = len(
                list(
                    session.exec(
                        select(SampleResource).where(SampleResource.sample_id == sample_id)
                    ).all()
                )
            )
            evaluations = len(
                list(
                    session.exec(
                        select(SampleTaskEvaluation).where(
                            SampleTaskEvaluation.sample_id == sample_id
                        )
                    ).all()
                )
            )
        if resources > 0 and evaluations > 0:
            return
        time.sleep(2)


async def test_researchrubrics_rollout(
    real_llm_stack: None,  # session fixture: stack up
    harness_client,  # poll /api/__danger__/test-harness/read/samples/{id}/state
    playwright_context,  # dashboard screenshots
    openrouter_budget: OpenRouterBudget | None,
) -> None:
    """End-to-end researchrubrics rollout against a real LLM.

    The rollout is the product: this test produces a snapshot the next
    agent session reads back.  We do not assert on scores, tool counts,
    node shapes, or UI content — only that the run reached a terminal
    state inside the time budget.
    """
    model = os.environ.get("ERGON_REAL_LLM_MODEL", _DEFAULT_MODEL)
    environment_name = "researchrubrics"
    worker = "research-runner"
    evaluator = "researchrubrics-rubric"
    limit = int(os.environ.get("ERGON_REAL_LLM_LIMIT", "1"))
    max_iterations = int(os.environ.get("ERGON_REAL_LLM_MAX_ITERATIONS", "16"))

    budget_before = (
        await openrouter_budget.remaining_usd() if openrouter_budget is not None else None
    )
    started_at = datetime.now(timezone.utc)

    sample_id, submission = await _submit_researchrubrics_sample(
        model=model,
        limit=limit,
        max_iterations=max_iterations,
    )

    terminal_state = harness_client.wait_for_terminal(
        sample_id,
        timeout_s=_HARNESS_POLL_TIMEOUT_SECONDS,
    )
    _wait_for_post_terminal_artifacts(sample_id)

    out_dir = rollout_dir(sample_id)

    # Persist submission metadata up front so a crashed DB dump still
    # leaves breadcrumbs for the reviewing agent.
    (out_dir / "submission.json").write_text(json.dumps(submission, indent=2, default=str))

    table_counts = dump_rollout(sample_id, out_dir)
    screenshots = await capture_dashboard(sample_id, playwright_context, out_dir)

    finished_at = datetime.now(timezone.utc)
    budget_after = (
        await openrouter_budget.remaining_usd() if openrouter_budget is not None else None
    )

    manifest_path = write_manifest(
        out_dir,
        sample_id=sample_id,
        benchmark=environment_name,
        worker=worker,
        evaluator=evaluator,
        model=model,
        cli_returncode=0,
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
        f"run {sample_id} did not reach a terminal status within "
        f"{_HARNESS_POLL_TIMEOUT_SECONDS}s — see {out_dir}"
    )
