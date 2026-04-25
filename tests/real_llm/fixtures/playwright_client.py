"""Playwright browser + context session fixtures for dashboard assertions."""

import asyncio
import os
from collections.abc import AsyncGenerator

import pytest

_PLAYWRIGHT_LAUNCH_TIMEOUT_SECONDS = 30.0
_PLAYWRIGHT_CONTEXT_TIMEOUT_SECONDS = 10.0


@pytest.fixture(scope="session")
async def playwright_browser() -> AsyncGenerator[object | None, None]:  # slopcop: ignore[no-typing-any]
    try:
        # reason: playwright is an optional dependency; skip gracefully if absent
        from playwright.async_api import async_playwright
    except ImportError:
        yield None
        return

    async with async_playwright() as pw:
        try:
            browser = await asyncio.wait_for(
                pw.chromium.launch(),
                timeout=_PLAYWRIGHT_LAUNCH_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            yield None
            return
        yield browser
        await browser.close()


@pytest.fixture
async def playwright_context(
    playwright_browser: object | None,
) -> AsyncGenerator[object | None, None]:  # slopcop: ignore[no-typing-any]
    if playwright_browser is None:
        yield None
        return
    try:
        ctx = await asyncio.wait_for(
            playwright_browser.new_context(
                base_url=os.environ.get("ERGON_DASHBOARD_URL", "http://127.0.0.1:3001"),
            ),
            timeout=_PLAYWRIGHT_CONTEXT_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        yield None
        return
    yield ctx
    await ctx.close()
