"""Integration smoke test for the /api/test/* test-harness endpoints.

Round-trips against a real running server + Postgres:
  seed -> read state -> reset -> verify gone (404)

Requires:
  - Server running at ERGON_API_BASE_URL (default http://127.0.0.1:9000)
    with ENABLE_TEST_HARNESS=1 and TEST_HARNESS_SECRET matching SECRET.
  - Postgres reachable at ERGON_DATABASE_URL.

Skipped automatically when the API or database is unreachable.
"""

import os

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from ergon_core.core.persistence.definitions.models import ExperimentDefinition
from ergon_core.core.persistence.shared.db import get_engine, get_session

pytestmark = pytest.mark.integration

API = os.environ.get("ERGON_API_BASE_URL", "http://127.0.0.1:9000")
SECRET = os.environ.get("TEST_HARNESS_SECRET", "local-dev")

_HEADERS = {"X-Test-Secret": SECRET}
_COHORT_PREFIX = "ci-smoke-"
_COHORT = "ci-smoke-harness-test"

# ---------------------------------------------------------------------------
# Connectivity helpers (extracted to avoid nested try blocks)
# ---------------------------------------------------------------------------


def _probe_harness_mounted() -> None:
    """Skip the session if the API is unreachable or the test-harness is not mounted.

    Probes POST /api/test/write/reset without the secret header:
      - harness mounted     → 401 (secret gate)
      - harness not mounted → 404 (route missing)
      - API unreachable     → ConnectError (caught and skipped)
    """
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.post(f"{API}/api/test/write/reset", json={"cohort_prefix": "probe"})
    except (httpx.ConnectError, httpx.ReadTimeout):
        pytest.skip("API unreachable — skipping harness integration tests")

    if resp.status_code != 401:
        pytest.skip(
            f"Test harness not mounted (expected 401, got {resp.status_code}) "
            "— skipping harness integration tests"
        )


def _probe_db_reachable() -> None:
    """Raise ``pytest.skip.Exception`` if the database is not reachable."""
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except OperationalError:
        pytest.skip("Database unreachable — skipping harness integration tests")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session", autouse=True)
def _probe_connectivity() -> None:
    """Skip the entire session if the API or database is unreachable."""
    _probe_harness_mounted()
    _probe_db_reachable()


@pytest.fixture(autouse=True)
def _reset_before_each() -> None:
    """Wipe any ci-smoke-* rows before each test for a clean slate."""
    try:
        with httpx.Client(timeout=10.0) as client:
            client.post(
                f"{API}/api/test/write/reset",
                json={"cohort_prefix": _COHORT_PREFIX},
                headers=_HEADERS,
            )
    except (httpx.ConnectError, httpx.ReadTimeout):
        pass  # session fixture already skipped if truly unreachable


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------


def test_seed_then_read_then_reset_roundtrip() -> None:
    """Seed a run, read its state, reset it, verify 404."""

    # ── Step 1: create an ExperimentDefinition via the ORM ──────────────────
    with get_session() as session:
        defn = ExperimentDefinition(benchmark_type="ci-smoke-harness")
        session.add(defn)
        session.commit()
        session.refresh(defn)
        defn_id = defn.id

    try:
        # ── Step 2: seed a run via POST /api/test/write/run/seed ─────────────────
        with httpx.Client(timeout=10.0) as client:
            seed_resp = client.post(
                f"{API}/api/test/write/run/seed",
                json={
                    "experiment_definition_id": str(defn_id),
                    "cohort": _COHORT,
                    "status": "completed",
                },
                headers=_HEADERS,
            )

        assert seed_resp.status_code == 201, seed_resp.text
        run_id = seed_resp.json()["run_id"]
        assert run_id  # non-empty UUID string

        # ── Step 3: read state via GET /api/test/read/run/{run_id}/state ─────────
        with httpx.Client(timeout=10.0) as client:
            state_resp = client.get(f"{API}/api/test/read/run/{run_id}/state")

        assert state_resp.status_code == 200, state_resp.text
        body = state_resp.json()
        assert body["run_id"] == run_id
        assert body["status"] == "completed"

        # ── Step 4: reset via POST /api/test/write/reset ─────────────────────────
        with httpx.Client(timeout=10.0) as client:
            reset_resp = client.post(
                f"{API}/api/test/write/reset",
                json={"cohort_prefix": _COHORT_PREFIX},
                headers=_HEADERS,
            )

        assert reset_resp.status_code == 204, reset_resp.text

        # ── Step 5: confirm the run is gone ──────────────────────────────────────
        with httpx.Client(timeout=10.0) as client:
            gone_resp = client.get(f"{API}/api/test/read/run/{run_id}/state")

        assert gone_resp.status_code == 404, gone_resp.text

    finally:
        # ── Cleanup: delete the ExperimentDefinition row to avoid leaks ──────────
        with get_session() as session:
            row = session.get(ExperimentDefinition, defn_id)
            if row is not None:
                session.delete(row)
                session.commit()
