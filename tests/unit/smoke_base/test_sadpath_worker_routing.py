"""``ResearchRubricsSadPathSmokeWorker`` routes ``l_2`` to the failing leaf.

Asserts only the override behaviour — the parent ``execute`` is
``@final`` and tested in ``test_smoke_worker_base_final.py``.
"""

from uuid import uuid4

from ergon_core.core.persistence.shared.types import AssignedWorkerSlug, TaskSlug
from tests.e2e._fixtures.workers.researchrubrics_smoke_sadpath import (
    ResearchRubricsSadPathSmokeWorker,
)


def _worker() -> ResearchRubricsSadPathSmokeWorker:
    return ResearchRubricsSadPathSmokeWorker(
        name="unit-test",
        model=None,
        task_id=uuid4(),
        sandbox_id="sbx-unit",
    )


def test_l_2_routed_to_failing_leaf() -> None:
    worker = _worker()
    spec = worker._spec_for("l_2", ("l_1",), "Line 2")
    assert spec.task_slug == TaskSlug("l_2")
    assert spec.assigned_worker_slug == AssignedWorkerSlug(
        "researchrubrics-smoke-leaf-failing",
    )
    assert spec.depends_on == [TaskSlug("l_1")]


def test_all_other_slugs_use_happy_leaf() -> None:
    worker = _worker()
    for slug in ("d_root", "d_left", "d_right", "d_join", "l_1", "l_3", "s_a", "s_b"):
        spec = worker._spec_for(slug, (), "…")
        assert spec.assigned_worker_slug == AssignedWorkerSlug(
            "researchrubrics-smoke-leaf",
        ), f"{slug} should use happy leaf, got {spec.assigned_worker_slug}"


def test_only_l_2_is_in_failing_slugs() -> None:
    """Sanity: future additions to FAILING_SLUGS should be conscious.
    If this assertion tightens, the sad-path driver's invariants must
    be updated in lock-step (8 messages vs 7, partial count, etc.)."""
    assert ResearchRubricsSadPathSmokeWorker.FAILING_SLUGS == frozenset({"l_2"})
