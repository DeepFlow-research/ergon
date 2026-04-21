"""docker-compose up/down session fixture with --assume-stack-up flag."""

import subprocess
import time
from collections.abc import Generator

import httpx
import pytest

_COMPOSE_FILE = "docker-compose.real-llm.yml"
_API_URL = "http://127.0.0.1:9000"
_DASHBOARD_URL = "http://127.0.0.1:3101"
_UP_TIMEOUT_S = 120


def _wait_for(url: str, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with httpx.Client(timeout=2.0) as client:
                client.get(url)
            return
        except (httpx.ConnectError, httpx.ReadTimeout):
            time.sleep(2.0)
    raise RuntimeError(f"timed out waiting for {url}")


@pytest.fixture(scope="session")
def real_llm_stack(request: pytest.FixtureRequest) -> Generator[None, None, None]:
    if request.config.getoption("--assume-stack-up"):
        _wait_for(f"{_API_URL}/health", 10)
        _wait_for(f"{_DASHBOARD_URL}", 10)
        yield
        return

    subprocess.run(
        ["docker", "compose", "-f", _COMPOSE_FILE, "up", "-d", "--wait"],
        check=True,
    )
    try:
        _wait_for(f"{_API_URL}/health", _UP_TIMEOUT_S)
        _wait_for(f"{_DASHBOARD_URL}", _UP_TIMEOUT_S)
        yield
    finally:
        subprocess.run(
            ["docker", "compose", "-f", _COMPOSE_FILE, "down", "-v"],
            check=False,
        )
