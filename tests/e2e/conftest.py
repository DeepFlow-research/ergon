"""Shared fixtures for E2E benchmark tests.

These tests run against a live docker-compose stack (postgres + inngest + api)
and require ERGON_DATABASE_URL to point at the shared Postgres instance.
"""

import os
import socket
import subprocess
from urllib.parse import urlparse

import pytest
from ergon_core.core.persistence.shared.db import get_engine
from ergon_core.core.settings import settings
from sqlmodel import Session

# Import side-effect: registers the per-env canonical-smoke workers,
# leaves, and criteria into ergon_builtins.registry's WORKERS /
# EVALUATORS dicts for the duration of the test session.  Phase B lands
# this as an empty hook; Phase C / D populate it.  Keeping the import at
# session-module scope means any e2e test that runs through conftest
# sees the registrations.
import tests.e2e._fixtures  # noqa: F401  (registration side-effect)


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
    probe Postgres and Inngest and fail loudly if either is down, unless
    ERGON_SKIP_INFRA_CHECK=1 is set.
    """
    if os.environ.get("ERGON_SKIP_INFRA_CHECK") == "1":
        return

    url = os.environ.get("ERGON_DATABASE_URL") or os.environ.get("DATABASE_URL", "")
    if not url:
        pytest.fail(
            "E2E tests require ERGON_DATABASE_URL pointing at a live Postgres. "
            "Run with docker-compose.ci.yml, or set ERGON_SKIP_INFRA_CHECK=1 to bypass."
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
        "Fix by starting the dev stack (docker compose up -d),",
        "or set ERGON_SKIP_INFRA_CHECK=1 to bypass intentionally.",
        "",
    ]
    pytest.fail("\n".join(lines))


@pytest.fixture(scope="session")
def db_session():
    """Provide a raw SQLModel session for assertion queries."""
    engine = get_engine()
    session = Session(engine)
    yield session
    session.close()


def run_benchmark(
    slug: str,
    *,
    worker: str,
    evaluator: str,
    limit: int = 1,
    cohort: str = "ci",
    timeout: int = 120,
) -> subprocess.CompletedProcess:
    """Run a benchmark via the ergon CLI and return the process result."""
    cmd = [
        "ergon",
        "benchmark",
        "run",
        slug,
        "--worker",
        worker,
        "--evaluator",
        evaluator,
        "--limit",
        str(limit),
        "--cohort",
        cohort,
        "--timeout",
        str(timeout),
    ]
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    return subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=timeout + 30)


@pytest.fixture(scope="session")
def benchmarked():
    """Memoize `run_benchmark` calls by (slug, worker, evaluator, cohort).

    The stubbed E2E tests each assert against the *latest* RunRecord; re-running
    the same benchmark per-test burned ~4× subprocess launches with identical
    outcomes. This fixture runs each unique config exactly once per session and
    returns the cached `CompletedProcess`.
    """
    cache: dict[tuple[str, str, str, str], subprocess.CompletedProcess] = {}

    def _run(
        slug: str,
        *,
        worker: str,
        evaluator: str,
        limit: int = 1,
        cohort: str = "ci",
        timeout: int = 120,
    ) -> subprocess.CompletedProcess:
        key = (slug, worker, evaluator, cohort)
        if key not in cache:
            cache[key] = run_benchmark(
                slug,
                worker=worker,
                evaluator=evaluator,
                limit=limit,
                cohort=cohort,
                timeout=timeout,
            )
        return cache[key]

    return _run
