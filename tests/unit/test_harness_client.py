"""Unit tests for BackendHarnessClient — async harness poller."""

import pytest
from pytest_httpx import HTTPXMock

from tests.real_llm.fixtures.harness_client import BackendHarnessClient


@pytest.mark.asyncio
async def test_wait_for_terminal_returns_on_completed(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url="http://example/api/test/read/run/run-1/state",
        json={"status": "completed", "graph_nodes": []},
    )
    client = BackendHarnessClient("http://example")
    state = await client.wait_for_terminal("run-1", timeout_s=5.0, poll_s=0.1)
    assert state["status"] == "completed"


@pytest.mark.asyncio
async def test_wait_for_terminal_polls_until_terminal(httpx_mock: HTTPXMock) -> None:
    url = "http://example/api/test/read/run/run-2/state"
    httpx_mock.add_response(url=url, json={"status": "running"})
    httpx_mock.add_response(url=url, json={"status": "running"})
    httpx_mock.add_response(url=url, json={"status": "failed"})
    client = BackendHarnessClient("http://example")
    state = await client.wait_for_terminal("run-2", timeout_s=5.0, poll_s=0.05)
    assert state["status"] == "failed"


@pytest.mark.asyncio
async def test_wait_for_terminal_times_out(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url="http://example/api/test/read/run/run-3/state",
        json={"status": "running"},
        is_reusable=True,
    )
    client = BackendHarnessClient("http://example")
    with pytest.raises(TimeoutError):
        await client.wait_for_terminal("run-3", timeout_s=0.3, poll_s=0.05)
