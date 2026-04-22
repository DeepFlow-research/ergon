"""Session-level prerequisites check.

Fails fast at session start if required infrastructure isn't reachable,
instead of letting every test silently burn ~30s of Inngest retry backoff
per event (5 attempts, exponential with jitter, starting at 100ms).

Opt out with ERGON_SKIP_INFRA_CHECK=1 when you knowingly want to run
against a missing backend (e.g. debugging retry paths).
"""

import os
import socket
from urllib.parse import urlparse

import pytest
from ergon_core.core.settings import settings


def _probe_tcp(host: str, port: int, timeout: float = 0.5) -> str | None:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return None
    except OSError as err:
        return f"{err.__class__.__name__}: {err}"


def pytest_sessionstart(session: pytest.Session) -> None:
    if os.environ.get("ERGON_SKIP_INFRA_CHECK") == "1":
        return

    parsed = urlparse(settings.inngest_api_base_url)
    host = parsed.hostname or "localhost"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)

    err = _probe_tcp(host, port)
    if err is None:
        return

    pytest.exit(
        "\n".join(
            [
                "",
                "Required infrastructure is NOT reachable — aborting test session.",
                "",
                f"  inngest_api_base_url = {settings.inngest_api_base_url}",
                f"  probe                = tcp://{host}:{port}",
                f"  error                = {err}",
                "",
                "Without Inngest, every unmocked `inngest_client.send(...)` retries 5×",
                "with exponential backoff (~3s per call). The 15-step DAG scenario",
                "alone turns into ~170s of pure retry waits.",
                "",
                "Fix by starting the dev stack (see docs/architecture/07_testing.md),",
                "or set ERGON_SKIP_INFRA_CHECK=1 to bypass this check intentionally.",
                "",
            ]
        ),
        returncode=2,
    )
