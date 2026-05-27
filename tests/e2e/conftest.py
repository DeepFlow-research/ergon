"""Shared fixtures for E2E benchmark tests.

These tests run against a live docker-compose stack (postgres + inngest + api)
and require ERGON_DATABASE_URL to point at the shared Postgres instance.
"""

import os
import socket
from urllib.parse import urlparse

import pytest
from ergon_core.core.shared.settings import settings

# NOTE: smoke fixture registration now lives exclusively inside the local API
# composition target.
# Host-side pytest is a black-box client (``_submit.py`` → HTTP) and
# doesn't need the fixtures in its own process.  Keeping the registry
# single-sourced eliminates the drift window where a fixture edit
# landed on one side but the other was running stale code.


def _probe_tcp(host: str, port: int, timeout: float = 0.5) -> str | None:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return None
    except OSError as err:
        return f"{err.__class__.__name__}: {err}"


@pytest.fixture(scope="session", autouse=True)
def _require_infra():
    """Fail fast if the E2E stack isn't reachable.

    Previously this silent-skipped when ERGON_DATABASE_URL was unset, which
    hid CI misconfigurations as "0 tests collected, green build". Now we also
    probe Postgres and Inngest and fail loudly if either is down.
    """
    url = os.environ.get("ERGON_DATABASE_URL") or os.environ.get("DATABASE_URL", "")
    if not url:
        pytest.fail(
            "E2E tests require ERGON_DATABASE_URL pointing at a live Postgres. "
            "Run with docker compose up -d."
        )

    db_parsed = urlparse(url)
    db_host = db_parsed.hostname or "localhost"
    db_port = db_parsed.port or 5432
    db_err = _probe_tcp(db_host, db_port)

    ing_parsed = urlparse(settings.inngest_api_base_url)
    ing_host = ing_parsed.hostname or "localhost"
    ing_port = ing_parsed.port or (443 if ing_parsed.scheme == "https" else 80)
    ing_err = _probe_tcp(ing_host, ing_port)

    if db_err is None and ing_err is None:
        return

    lines = ["", "E2E infrastructure is NOT reachable — aborting.", ""]
    if db_err is not None:
        lines.append(f"  postgres  = tcp://{db_host}:{db_port}  error: {db_err}")
    if ing_err is not None:
        lines.append(f"  inngest   = tcp://{ing_host}:{ing_port}  error: {ing_err}")
    lines += [
        "",
        "Fix by starting the dev stack (docker compose up -d).",
        "",
    ]
    pytest.fail("\n".join(lines))
