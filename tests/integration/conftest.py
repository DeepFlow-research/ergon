"""Tier-scoped preflight + singleton rebind for the integration test suite.

Guards `tests/integration/` — the tier that drives through the real Inngest
dev server and real Postgres. Does two things:

1. Fails fast at session start if Inngest is unreachable, instead of letting
   every test silently burn ~30 s of Inngest retry backoff per event
   (5 attempts, exponential with jitter, starting at 100 ms).
2. Rebinds the process-wide ``inngest_client`` HTTP client per test so the
   function-scoped event loops that pytest-asyncio creates don't leave the
   singleton holding a closed loop's httpcore connection pool.

This preflight is deliberately NOT at `tests/conftest.py` — the
`tests/unit/` tier runs without the integration Inngest/Postgres stack and
must not be gated on this preflight. Scoping is by filesystem path, per
`docs/architecture/07_testing.md` §4.

Opt out of the preflight with ERGON_SKIP_INFRA_CHECK=1 when you knowingly
want to run against a missing backend (e.g. debugging retry paths).
"""

import os
import socket
from urllib.parse import urlparse

import pytest
import pytest_asyncio
from ergon_core.core.runtime.inngest_client import inngest_client
from ergon_core.core.settings import settings
from inngest._internal import net as inngest_net


@pytest_asyncio.fixture(autouse=True)
async def _reset_inngest_http_client():
    """Rebind ``inngest_client`` to the current test's event loop.

    ``inngest_client`` is a process-wide singleton. Its internal
    ``httpx.AsyncClient`` (and the underlying ``httpcore`` connection
    pool) gets bound to the event loop of the *first* ``send`` call in
    the process. Under pytest-asyncio's default function-scoped loops,
    the second async test inherits a connection pool whose loop is
    already closed, so every ``inngest_client.send`` raises
    ``RuntimeError: Event loop is closed``.

    Replacing ``_http_client`` before each test forces the singleton to
    (re)initialize inside the active test's loop — the connection pool
    is re-created lazily on the next request. We close the outgoing
    client afterwards to keep resource bookkeeping tidy.
    """
    old = inngest_client._http_client  # type: ignore[attr-defined]
    inngest_client._http_client = inngest_net.AuthenticatedHTTPClient(  # type: ignore[attr-defined]
        env=old._env,
        signing_key=old._signing_key,
        signing_key_fallback=old._signing_key_fallback,
    )
    try:
        yield
    finally:
        fresh = inngest_client._http_client  # type: ignore[attr-defined]
        try:
            await fresh._http_client.aclose()
        except Exception:
            pass


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
                "Required infrastructure is NOT reachable — aborting integration tests.",
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
