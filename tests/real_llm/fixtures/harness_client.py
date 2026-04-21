"""Python twin of the TS testHarnessClient.ts for /api/test/read/* endpoints."""

import os
import time
from typing import Any

import httpx
import pytest


class BackendHarnessClient:
    """Poll the test harness read endpoints for run/task state."""

    def __init__(self, base_url: str) -> None:
        self._base = base_url

    def get_run_state(self, run_id: str) -> dict[str, Any]:  # slopcop: ignore[no-typing-any]
        with httpx.Client(timeout=10.0) as client:
            r = client.get(f"{self._base}/api/test/read/run/{run_id}/state")
            r.raise_for_status()
            return r.json()

    def wait_for_terminal(
        self,
        run_id: str,
        *,
        timeout_s: float = 600.0,
        poll_s: float = 3.0,
    ) -> dict[str, Any]:  # slopcop: ignore[no-typing-any]
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            state = self.get_run_state(run_id)
            if state["status"] in {"completed", "failed", "cancelled"}:
                return state
            time.sleep(poll_s)
        raise TimeoutError(f"run {run_id} did not reach terminal status in {timeout_s}s")


@pytest.fixture
def harness_client() -> BackendHarnessClient:
    return BackendHarnessClient(os.environ.get("ERGON_API_BASE_URL", "http://127.0.0.1:9000"))
