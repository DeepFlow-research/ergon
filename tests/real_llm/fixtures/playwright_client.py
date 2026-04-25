"""Playwright browser + context session fixtures for dashboard assertions."""

import os
from collections.abc import AsyncGenerator

import pytest


@pytest.fixture(scope="session")
async def playwright_browser() -> AsyncGenerator[object, None]:  # slopcop: ignore[no-typing-any]
    try:
        # reason: playwright is an optional dependency; skip gracefully if absent
        from playwright.async_api import async_playwright
    except ImportError:
        pytest.skip("playwright not installed — skipping dashboard-assertion tests")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        yield browser
        await browser.close()


@pytest.fixture
async def playwright_context(
    playwright_browser: object,
) -> AsyncGenerator[object, None]:  # slopcop: ignore[no-typing-any]
    ctx = await playwright_browser.new_context(
        base_url=os.environ.get("ERGON_DASHBOARD_URL", "http://127.0.0.1:3101"),
    )
    yield ctx
    await ctx.close()
