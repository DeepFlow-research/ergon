"""Dispatcher for the OpenRouter budget gate only activates under the
``real_llm_billing`` marker.

Bug: `docs/bugs/open/2026-04-21-budget-gate-autouse-skips-stub-canary.md`.

The previous gate was `autouse=True` and transitively pulled in
``openrouter_budget``, which skips when ``OPENROUTER_API_KEY`` is absent. That
cascaded into the stub canary. The fix splits the gate into an opt-in
``enforce_openrouter_budget`` fixture and a tiny autouse dispatcher
``_maybe_enforce_budget`` that only requests it when the test is marked
``real_llm_billing``.
"""

from __future__ import annotations

from typing import Any

from tests.real_llm.fixtures.openrouter_budget import _maybe_enforce_budget


class _MockRequest:
    """Minimal stand-in for ``pytest.FixtureRequest``.

    We only exercise the two attributes the dispatcher touches: ``keywords``
    (membership test against the marker name) and ``getfixturevalue``.
    """

    def __init__(self, keywords: dict[str, Any]) -> None:
        self.keywords = keywords
        self.calls: list[str] = []

    def getfixturevalue(self, name: str) -> None:
        self.calls.append(name)


def _dispatcher_fn() -> Any:
    """Return the underlying dispatcher function, unwrapping the pytest fixture."""
    return _maybe_enforce_budget.__wrapped__  # type: ignore[attr-defined]


def test_dispatcher_skips_fixture_without_marker() -> None:
    """Unmarked tests must not pull in ``enforce_openrouter_budget``."""
    request = _MockRequest(keywords={})

    result = _dispatcher_fn()(request)

    assert result is None
    assert request.calls == [], (
        "dispatcher must NOT request enforce_openrouter_budget for unmarked tests"
    )


def test_dispatcher_requests_fixture_with_marker() -> None:
    """Tests marked ``real_llm_billing`` must pull in the budget gate."""
    request = _MockRequest(keywords={"real_llm_billing": True})

    _dispatcher_fn()(request)

    assert request.calls == ["enforce_openrouter_budget"], (
        "dispatcher must request enforce_openrouter_budget for marked tests"
    )


def test_dispatcher_ignores_unrelated_markers() -> None:
    """Other markers (e.g. ``real_llm``, ``asyncio``) must not trigger the gate."""
    request = _MockRequest(keywords={"real_llm": True, "asyncio": True})

    _dispatcher_fn()(request)

    assert request.calls == [], "dispatcher must only react to the real_llm_billing marker"
