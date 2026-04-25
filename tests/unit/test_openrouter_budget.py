"""OpenRouterBudget: snapshot baseline, compute delta, gate spend."""

from unittest.mock import AsyncMock, patch

import pytest

from ergon_core.core.providers.generation.openrouter_budget import OpenRouterBudget


def _make_mock_response(
    usage: float, limit: float = 100.0, limit_remaining: float = 97.5
) -> object:
    class _Resp:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"data": {"usage": usage, "limit": limit, "limit_remaining": limit_remaining}}

    return _Resp()


@pytest.mark.asyncio
async def test_remaining_usd_returns_limit_minus_delta() -> None:
    budget = OpenRouterBudget(limit_usd=5.0, api_key="test-key")

    async def _mock_get(*_args: object, **_kwargs: object) -> object:
        return _make_mock_response(usage=2.50, limit_remaining=97.50)

    with patch("httpx.AsyncClient.get", new=AsyncMock(side_effect=_mock_get)):
        await budget.snapshot_baseline()

        # usage is same as baseline on first call => spent 0, remaining = limit
        assert (await budget.remaining_usd()) == pytest.approx(5.0)


@pytest.mark.asyncio
async def test_remaining_usd_after_spend() -> None:
    budget = OpenRouterBudget(limit_usd=5.0, api_key="test-key")

    # First call sets baseline at usage=2.50; second call reports usage=3.70;
    # delta is 1.20; remaining = 5.0 - 1.20 = 3.80.
    usages = iter([2.50, 3.70])

    async def _mock_get(*_args: object, **_kwargs: object) -> object:
        return _make_mock_response(usage=next(usages))

    with patch("httpx.AsyncClient.get", new=AsyncMock(side_effect=_mock_get)):
        await budget.snapshot_baseline()
        assert (await budget.remaining_usd()) == pytest.approx(3.80)


@pytest.mark.asyncio
async def test_remaining_usd_raises_without_snapshot() -> None:
    budget = OpenRouterBudget(limit_usd=5.0, api_key="test-key")

    with pytest.raises(RuntimeError, match="baseline"):
        await budget.remaining_usd()
