"""Unit test for the real-LLM DB-URL override fixture.

Guards the P0 regression where the parent pytest process, seeing an
``.env``-loaded ``ERGON_DATABASE_URL`` pointing at a developer's own DB,
would fail to query the compose-overlay Postgres after the canary
subprocess succeeded.

The ``pytester`` builtin isn't wired into this repo's pytest config, so we
exercise the fixture's underlying generator function (``_apply_override``)
directly: preload a bogus ``ERGON_DATABASE_URL`` on a ``MonkeyPatch``,
drive the generator, and assert the env now matches the compose overlay.
"""

import os

import pytest

from tests.real_llm.fixtures.database import _COMPOSE_DATABASE_URL, _apply_override


def test_override_database_url_pins_to_compose_overlay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The fixture overrides any preexisting ``ERGON_DATABASE_URL`` with the overlay URL."""
    monkeypatch.setenv("ERGON_DATABASE_URL", "postgresql://wrong:wrong@127.0.0.1:5432/wrong")

    gen = _apply_override(monkeypatch)
    next(gen)  # run setup

    assert os.environ["ERGON_DATABASE_URL"] == _COMPOSE_DATABASE_URL

    with pytest.raises(StopIteration):
        next(gen)  # drive teardown to exhaustion


def test_override_database_url_sets_when_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The fixture sets ``ERGON_DATABASE_URL`` when the parent env had none."""
    monkeypatch.delenv("ERGON_DATABASE_URL", raising=False)

    gen = _apply_override(monkeypatch)
    next(gen)

    assert os.environ["ERGON_DATABASE_URL"] == _COMPOSE_DATABASE_URL

    with pytest.raises(StopIteration):
        next(gen)
