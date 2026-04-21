"""Force the parent pytest process to use the compose-overlay Postgres."""

from collections.abc import Generator

import pytest

_COMPOSE_DATABASE_URL = "postgresql://ergon:ergon@127.0.0.1:5433/ergon"


def _apply_override(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    """Core override logic — broken out for direct unit testing.

    Pins ``ERGON_DATABASE_URL`` to the compose-overlay URL on the parent
    pytest process (and, transitively, any subprocesses that inherit
    ``os.environ``).
    """
    monkeypatch.setenv("ERGON_DATABASE_URL", _COMPOSE_DATABASE_URL)
    yield


@pytest.fixture(autouse=True)
def _override_database_url(
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[None, None, None]:
    """Pin the real-LLM tier to the compose-overlay DB.

    Without this, ``.env``-loaded ``ERGON_DATABASE_URL`` would point at the
    developer's own local DB (wrong password, wrong port), causing the
    parent pytest process to fail post-subprocess DB queries.
    """
    yield from _apply_override(monkeypatch)
