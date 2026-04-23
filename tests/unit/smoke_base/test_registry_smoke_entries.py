"""Importing ``tests.e2e._fixtures`` populates the expected smoke slugs.

Phase C registers the researchrubrics happy + sad-path rows.  Phase D
adds minif2f and swebench-verified.  This test expects exactly what's
registered as of the current phase — update the expected sets when
adding env fixtures.
"""

import pytest


def test_researchrubrics_slugs_registered() -> None:
    import tests.e2e._fixtures  # noqa: F401  (import side-effect)
    from ergon_builtins.registry import EVALUATORS, WORKERS

    expected_workers = {
        "researchrubrics-smoke-worker",
        "researchrubrics-smoke-leaf",
        "researchrubrics-sadpath-smoke-worker",
        "researchrubrics-smoke-leaf-failing",
    }
    for slug in expected_workers:
        assert slug in WORKERS, f"worker slug missing from registry: {slug}"

    assert "researchrubrics-smoke-criterion" in EVALUATORS


def test_no_retired_slugs_present() -> None:
    """Retired smoke slugs should not appear under the test-fixture
    registrations.  Legacy ``canonical-smoke`` worker may still be
    registered by the non-test registry path until Phase F deletions,
    so we don't assert it's absent — only that we haven't re-introduced
    it from the fixtures side.
    """
    import importlib

    fixtures = importlib.import_module("tests.e2e._fixtures")
    # Fixtures module exposes only register_smoke_fixtures and the
    # imported classes; no "canonical-smoke" symbol should leak.
    assert not hasattr(fixtures, "CanonicalSmokeWorker"), (
        "fixtures must not re-export the retired CanonicalSmokeWorker"
    )


def test_register_is_idempotent() -> None:
    """Calling register_smoke_fixtures twice doesn't raise / duplicate."""
    from tests.e2e._fixtures import register_smoke_fixtures

    register_smoke_fixtures()
    register_smoke_fixtures()


@pytest.mark.skip(reason="Phase D populates minif2f and swebench fixtures")
def test_minif2f_slugs_registered() -> None:
    pass


@pytest.mark.skip(reason="Phase D populates minif2f and swebench fixtures")
def test_swebench_slugs_registered() -> None:
    pass
