"""Session-scoped OpenRouter budget fixture + conditional cost gate."""

import os
from collections.abc import AsyncGenerator

import pytest

from ergon_core.core.providers.generation.openrouter_budget import OpenRouterBudget


@pytest.fixture(scope="session")
async def openrouter_budget() -> AsyncGenerator[OpenRouterBudget | None, None]:
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        yield None
        return
    limit = float(os.environ.get("ERGON_REAL_LLM_BUDGET_USD", "5.0"))
    budget = OpenRouterBudget(limit_usd=limit, api_key=key)
    await budget.snapshot_baseline()
    yield budget


@pytest.fixture(autouse=True)
async def _budget_gate(openrouter_budget: OpenRouterBudget | None) -> None:
    if openrouter_budget is None:
        return
    remaining = await openrouter_budget.remaining_usd()
    if remaining <= 0:
        pytest.skip(f"OpenRouter budget exhausted (remaining=${remaining:.2f})")
