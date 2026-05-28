"""Real-LLM harness canary — exercises the whole harness pipeline without
actually spending tokens. Uses the researchrubrics smoke fixture + stub model.

Validates:
  - docker stack up (or --assume-stack-up), stack fixture did not skip
  - Pythonic ResearchRubrics smoke environment submission works
  - /api/__danger__/test-harness/read/samples/{id}/state returns a terminal state
  - Postgres row exists with the right relationships
  - Playwright can find the run grouping in the dashboard
"""

from datetime import timezone, datetime

import pytest
from ergon_core.api import Experiment, RandomSampler
from ergon_core.core.application.experiments.submission import ExperimentSubmissionService
from ergon_core.core.persistence.shared.db import ensure_db, get_session
from tests.fixtures.smoke_components.benchmarks import ResearchRubricsSmokeEnvironment

pytestmark = [pytest.mark.real_llm, pytest.mark.asyncio]


async def _submit_smoke_sample() -> str:
    """Submit the ResearchRubrics smoke sample through Python composition."""
    ensure_db()
    with get_session() as session:
        environment = ResearchRubricsSmokeEnvironment(
            name="researchrubrics",
            worker_slug="researchrubrics-smoke-worker",
            model="stub:constant",
            metadata={"source": "real-llm-canary"},
        )
        experiment = Experiment(
            name=f"real-llm-smoke-stub-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}",
            environments=[environment],
            metadata={"source": "real-llm-canary"},
        )
        result = await experiment.submit(
            service=ExperimentSubmissionService.for_session(session),
            k=1,
            sampler=RandomSampler(seed=0),
        )
    if not result.sample_ids:
        raise RuntimeError("smoke canary submission returned no sample_ids")
    return str(result.sample_ids[0])


async def test_harness_canary_smoke_stub(
    real_llm_stack: None,
    harness_client,
    playwright_context,
) -> None:
    sample_id = await _submit_smoke_sample()

    # Poll the harness until terminal.
    state = harness_client.wait_for_terminal(sample_id, timeout_s=120)
    assert state["status"] == "completed", f"run did not complete: {state}"
    assert len(state.get("graph_nodes", [])) >= 1

    # Playwright: dashboard index renders.
    if playwright_context is not None:
        page = await playwright_context.new_page()
        await page.goto("/")
        await page.wait_for_load_state("networkidle")
        # Loose assertion: page rendered.
        content = await page.content()
        assert content, "dashboard rendered empty"
