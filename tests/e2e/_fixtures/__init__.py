"""Test-only worker / criterion registration hook.

Importing this package registers the canonical-smoke per-env workers,
leaves, and criteria into the process-level ``WORKERS`` / ``EVALUATORS``
dicts from ``ergon_builtins.registry``.  Production CLI paths do not
import ``tests/``, so registrations here are confined to test runtimes.

Phase B (this commit) wires the hook with an empty ``register_smoke_fixtures``
function body.  Phase C adds the researchrubrics registrations; Phase D adds
minif2f and swebench.  Keeping the hook importable with no registrations
lets unit tests import the base classes in ``smoke_base`` without pulling in
env-specific fixtures that do not exist yet.

See docs/superpowers/plans/test-refactor/01-fixtures.md §2.7 for the full
registration story.
"""


def register_smoke_fixtures() -> None:
    """Register the 9 smoke worker + criterion slugs.

    Intentionally empty in Phase B.  Phase C populates the researchrubrics
    row; Phase D populates minif2f and swebench.  Always idempotent: calling
    twice is a no-op (``dict`` assignment is the mechanism).
    """


register_smoke_fixtures()
