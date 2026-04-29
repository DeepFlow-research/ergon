"""Immutable topology + slug constants for the canonical smoke DAG.

One place.  ``SmokeWorkerBase``, ``SmokeCriterionBase``, every pytest
driver, and every Playwright spec import from here.  Changing this tuple
is the only way to change smoke topology.

Shape: 4-node diamond + 3-node line + 2 singletons = 9 leaves.

    d_root ── d_left  ─┐
           └─ d_right ─┴─> d_join

    l_1 ──> l_2 ──> l_3

    s_a         s_b
"""

from collections.abc import Sequence

EXPECTED_SUBTASK_SLUGS: tuple[str, ...] = (
    "d_root",
    "d_left",
    "d_right",
    "d_join",
    "l_1",
    "l_2",
    "l_3",
    "s_a",
    "s_b",
)

# (slug, depends_on_slugs, description) — shape of the DAG in one place.
# Order is authoritative: ``SmokeWorkerBase.execute`` iterates this tuple
# in-order when calling ``plan_subtasks``.  Leaves appear before anything
# that depends on them so slug-level forward refs are avoided.
SUBTASK_GRAPH: Sequence[tuple[str, tuple[str, ...], str]] = (
    ("d_root", (), "Diamond root"),
    ("d_left", ("d_root",), "Diamond left arm"),
    ("d_right", ("d_root",), "Diamond right arm"),
    ("d_join", ("d_left", "d_right"), "Diamond join (two-parent fan-in)"),
    ("l_1", (), "Line node 1"),
    ("l_2", ("l_1",), "Line node 2"),
    ("l_3", ("l_2",), "Line node 3"),
    ("s_a", (), "Singleton A"),
    ("s_b", (), "Singleton B"),
)
