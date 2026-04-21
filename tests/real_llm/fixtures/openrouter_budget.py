"""Session-scoped OpenRouter budget fixture + marker-gated cost enforcement.

The budget gate is dispatched via a lightweight autouse fixture that only
activates for tests explicitly marked ``real_llm_billing``. Stub-only tests
(e.g. the canary) are unaffected and run with cost=0 regardless of
``OPENROUTER_API_KEY`` presence.
"""

import os
from collections.abc import AsyncGenerator

import pytest

from ergon_core.core.providers.generation.openrouter_budget import OpenRouterBudget


@pytest.fixture(scope="session")
async def openrouter_budget() -> AsyncGenerator[OpenRouterBudget, None]:
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        pytest.skip("OPENROUTER_API_KEY not set — skipping real-LLM tests")
    limit = float(os.environ.get("ERGON_REAL_LLM_BUDGET_USD", "5.0"))
    budget = OpenRouterBudget(limit_usd=limit, api_key=key)
    await budget.snapshot_baseline()
    yield budget


@pytest.fixture
async def enforce_openrouter_budget(
    openrouter_budget: OpenRouterBudget,
) -> None:
    """Skip the current test if the session-wide OpenRouter budget is exhausted.

    Opt-in via the ``real_llm_billing`` marker; see ``_maybe_enforce_budget``.
    """
    remaining = await openrouter_budget.remaining_usd()
    if remaining <= 0:
        pytest.skip(f"OpenRouter budget exhausted (remaining=${remaining:.2f})")


@pytest.fixture(autouse=True)
def _maybe_enforce_budget(
    request: pytest.FixtureRequest,
) -> None:
    """Request ``enforce_openrouter_budget`` only when the test is marked
    ``real_llm_billing``. Stub-only tests (e.g. the canary) are unaffected
    and run with cost=0 regardless of OPENROUTER_API_KEY presence."""
    if "real_llm_billing" in request.keywords:
        request.getfixturevalue("enforce_openrouter_budget")
