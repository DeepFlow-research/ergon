"""Test-owned smoke components.

Smoke components are imported explicitly by the tests that need them. The v2
runtime no longer has a process-local component registry to mutate at startup.
"""


def register_smoke_fixtures() -> None:
    """Compatibility no-op for older smoke harness entrypoints."""

    return None


register_smoke_components = register_smoke_fixtures
