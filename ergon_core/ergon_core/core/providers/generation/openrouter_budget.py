"""Track cumulative OpenRouter spend against a per-session budget.

Usage:
    budget = OpenRouterBudget(limit_usd=5.0, api_key=os.environ["OPENROUTER_API_KEY"])
    await budget.snapshot_baseline()  # at pytest session start
    ...
    if await budget.remaining_usd() <= 0:
        pytest.skip("OpenRouter budget exhausted")
"""

import httpx


_KEY_ENDPOINT = "https://openrouter.ai/api/v1/auth/key"


class OpenRouterBudget:
    """Snapshot cumulative OpenRouter spend and compare against a limit."""

    def __init__(self, *, limit_usd: float, api_key: str) -> None:
        self._limit = limit_usd
        self._api_key = api_key
        self._baseline: float | None = None

    async def snapshot_baseline(self) -> None:
        self._baseline = await self._current_usage()

    async def remaining_usd(self) -> float:
        if self._baseline is None:
            raise RuntimeError("snapshot_baseline must be called before remaining_usd")
        current = await self._current_usage()
        return self._limit - (current - self._baseline)

    async def _current_usage(self) -> float:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                _KEY_ENDPOINT,
                headers={"Authorization": f"Bearer {self._api_key}"},
            )
            resp.raise_for_status()
            return float(resp.json()["data"]["usage"])
