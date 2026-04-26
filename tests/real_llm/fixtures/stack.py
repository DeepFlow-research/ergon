"""docker-compose up/down session fixture with --assume-stack-up flag.

Uses the unified ``docker-compose.yml`` (no more ``docker-compose.real-llm.yml``);
real-LLM-specific configuration comes from env vars picked up by the
compose file's ``${VAR:-default}`` substitutions.
"""

import os
import subprocess
import time
from collections.abc import Generator

import httpx
import pytest

_API_URL = "http://127.0.0.1:9000"
_DASHBOARD_URL = "http://127.0.0.1:3001"
_UP_TIMEOUT_S = 120


def _wait_for(url: str, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with httpx.Client(timeout=2.0) as client:
                client.get(url)
            return
        except (httpx.ConnectError, httpx.ReadError, httpx.ReadTimeout):
            time.sleep(2.0)
    raise RuntimeError(f"timed out waiting for {url}")


@pytest.fixture(scope="session")
def real_llm_stack(request: pytest.FixtureRequest) -> Generator[None, None, None]:
    if request.config.getoption("--assume-stack-up"):
        _wait_for(f"{_API_URL}/", 10)
        _wait_for(_DASHBOARD_URL, 10)
        yield
        return

    # Real-LLM defaults: dedicated harness secret + real OpenRouter key
    # (inherited from the shell environment if set).  Unified compose
    # defaults to ``local-dev`` secret / empty OPENROUTER_API_KEY.
    env = {
        **os.environ,
        "TEST_HARNESS_SECRET": os.environ.get(
            "TEST_HARNESS_SECRET",
            "real-llm-secret",
        ),
    }
    subprocess.run(
        ["docker", "compose", "up", "-d", "--wait"],
        env=env,
        check=True,
    )
    try:
        _wait_for(f"{_API_URL}/", _UP_TIMEOUT_S)
        _wait_for(_DASHBOARD_URL, _UP_TIMEOUT_S)
        yield
    finally:
        subprocess.run(
            ["docker", "compose", "down", "-v"],
            check=False,
        )
