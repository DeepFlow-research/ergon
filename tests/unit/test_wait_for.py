"""`_wait_for` treats only 2xx as ready; 4xx/5xx/ConnectError keep polling."""

from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from tests.real_llm.fixtures import stack as stack_mod
from tests.real_llm.fixtures.stack import _wait_for


class _FakeClient:
    """Minimal httpx.Client stand-in supporting the context-manager + get() surface."""

    def __init__(self, responder: Any) -> None:
        self._responder = responder

    def __enter__(self) -> "_FakeClient":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def get(self, url: str) -> Any:
        return self._responder(url)


def _patch_client(monkeypatch: pytest.MonkeyPatch, responder: Any) -> None:
    def _factory(*_args: object, **_kwargs: object) -> _FakeClient:
        return _FakeClient(responder)

    monkeypatch.setattr(stack_mod.httpx, "Client", _factory)


def _patch_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    # reason: _wait_for calls time.sleep(2.0) between attempts; short-circuit it
    monkeypatch.setattr(stack_mod.time, "sleep", lambda _s: None)


def test_wait_for_returns_on_200(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_sleep(monkeypatch)
    _patch_client(monkeypatch, lambda _url: SimpleNamespace(status_code=200))
    # Should return without raising.
    _wait_for("http://fake/health", timeout=0.5)


def test_wait_for_raises_on_persistent_404(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_sleep(monkeypatch)
    _patch_client(monkeypatch, lambda _url: SimpleNamespace(status_code=404))
    with pytest.raises(RuntimeError, match="timed out waiting for"):
        _wait_for("http://fake/health", timeout=0.5)


def test_wait_for_raises_on_persistent_connect_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_sleep(monkeypatch)

    def _boom(_url: str) -> Any:
        raise httpx.ConnectError("refused")

    _patch_client(monkeypatch, _boom)
    with pytest.raises(RuntimeError, match="timed out waiting for"):
        _wait_for("http://fake/health", timeout=0.5)
