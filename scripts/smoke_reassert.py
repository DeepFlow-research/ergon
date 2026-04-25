"""Re-run smoke assertions against an already-completed run_id.

Lets you iterate on assertion logic (or debug a failing assertion) without
re-submitting the whole cohort through E2B — a 60s sandbox run becomes a
sub-second assertion pass.

Usage::

    uv run python scripts/smoke_reassert.py \\
        --run-id 8f3a… \\
        --env researchrubrics \\
        --kind happy

Positional behaviour: with ``--kind happy`` (default) runs the full
happy-path helper set; with ``--kind sad`` runs the sad-path helper set
(researchrubrics only).  Prints each assertion as it runs and surfaces
the first failure with a stack trace so you can edit + re-invoke.

Requires the same env the drivers do (``ERGON_DATABASE_URL``,
``ERGON_API_BASE_URL``, ``TEST_HARNESS_SECRET``).  Does NOT touch E2B,
Playwright, or docker-compose.
"""

from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path
from uuid import UUID

# Prepend repo root so ``tests.e2e.*`` imports resolve when running as
# a standalone script (pytest adds rootdir automatically; we don't).
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Register smoke fixtures so ``RunGenerationTurn`` schema imports + any
# runtime ClassVars (PARENT_TURN_COUNT etc.) are wired up identically to how
# the driver sees them.
from ergon_core.test_support.smoke_fixtures import register_smoke_fixtures

register_smoke_fixtures()
from tests.e2e._asserts import (
    _assert_blob_roundtrip,
    _assert_run_evaluation,
    _assert_run_graph,
    _assert_run_resources,
    _assert_run_turn_counts,
    _assert_sadpath_evaluation,
    _assert_sadpath_graph_cascade,
    _assert_sadpath_partial_artifact,
    _assert_sadpath_partial_wal,
    _assert_sadpath_thread_messages,
    _assert_sandbox_command_wal,
    _assert_sandbox_lifecycle_events,
    _assert_temporal_ordering,
    _assert_thread_messages_ordered,
)

HAPPY_ASSERTS = [
    ("graph", _assert_run_graph),
    ("resources", _assert_run_resources),
    ("turn_counts", _assert_run_turn_counts),
    ("sandbox_command_wal", _assert_sandbox_command_wal),
    ("sandbox_lifecycle_events", _assert_sandbox_lifecycle_events),
    ("thread_messages_ordered", _assert_thread_messages_ordered),
    ("blob_roundtrip", _assert_blob_roundtrip),
    ("temporal_ordering", _assert_temporal_ordering),
    ("run_evaluation", _assert_run_evaluation),
]

SAD_ASSERTS = [
    ("sadpath_graph_cascade", _assert_sadpath_graph_cascade),
    ("sadpath_partial_artifact", _assert_sadpath_partial_artifact),
    ("sadpath_partial_wal", _assert_sadpath_partial_wal),
    ("sadpath_thread_messages", _assert_sadpath_thread_messages),
    ("sadpath_evaluation", _assert_sadpath_evaluation),
    ("sandbox_command_wal", _assert_sandbox_command_wal),
    ("sandbox_lifecycle_events", _assert_sandbox_lifecycle_events),
    ("temporal_ordering", _assert_temporal_ordering),
]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run-id", required=True, type=UUID, help="Completed run UUID")
    p.add_argument(
        "--env",
        required=True,
        choices=("researchrubrics", "minif2f", "swebench-verified"),
        help="Benchmark env (kept for symmetry; only affects the label)",
    )
    p.add_argument(
        "--kind",
        default="happy",
        choices=("happy", "sad"),
        help="Happy = full happy-path asserts; sad = researchrubrics sad slot",
    )
    p.add_argument(
        "--stop-on-first-fail",
        action="store_true",
        help="Stop at the first failing assertion (default: run all, count failures)",
    )
    args = p.parse_args()

    asserts = HAPPY_ASSERTS if args.kind == "happy" else SAD_ASSERTS
    passed: list[str] = []
    failed: list[tuple[str, BaseException]] = []

    print(
        f"[smoke_reassert] run_id={args.run_id} env={args.env} kind={args.kind} "
        f"→ {len(asserts)} checks",
    )
    for name, fn in asserts:
        try:
            fn(args.run_id)
        except BaseException as exc:
            failed.append((name, exc))
            print(f"  ✗ {name}: {type(exc).__name__}: {exc}")
            if args.stop_on_first_fail:
                traceback.print_exc()
                break
        else:
            passed.append(name)
            print(f"  ✓ {name}")

    total = len(passed) + len(failed)
    print(
        f"[smoke_reassert] {len(passed)}/{total} passed, {len(failed)} failed",
    )
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
