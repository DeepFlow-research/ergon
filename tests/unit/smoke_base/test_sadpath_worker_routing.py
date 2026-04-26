"""``ResearchRubricsSadPathSmokeWorker`` routes ``l_2`` to the failing leaf.

Asserts only the override behaviour — the parent ``execute`` is
``@final`` and tested in ``test_smoke_worker_base_final.py``.
"""

from uuid import uuid4

from ergon_core.core.persistence.shared.types import AssignedWorkerSlug, TaskSlug
import pytest

from ergon_core.test_support.smoke_fixtures.workers.minif2f_smoke import (
    MiniF2FSadPathSmokeWorker,
)
from ergon_core.test_support.smoke_fixtures.workers.researchrubrics_smoke import (
    ResearchRubricsSadPathSmokeWorker,
)
from ergon_core.test_support.smoke_fixtures.workers.swebench_smoke import (
    SweBenchSadPathSmokeWorker,
)


@pytest.mark.parametrize(
    ("worker_cls", "happy_leaf", "failing_leaf"),
    [
        (
            ResearchRubricsSadPathSmokeWorker,
            "researchrubrics-smoke-leaf",
            "researchrubrics-smoke-leaf-failing",
        ),
        (MiniF2FSadPathSmokeWorker, "minif2f-smoke-leaf", "minif2f-smoke-leaf-failing"),
        (SweBenchSadPathSmokeWorker, "swebench-smoke-leaf", "swebench-smoke-leaf-failing"),
    ],
)
def test_l_2_routed_to_failing_leaf(worker_cls, happy_leaf: str, failing_leaf: str) -> None:
    worker = worker_cls(
        name="unit-test",
        model=None,
        task_id=uuid4(),
        sandbox_id="sbx-unit",
    )
    spec = worker._spec_for("l_2", ("l_1",), "Line 2")
    assert spec.task_slug == TaskSlug("l_2")
    assert spec.assigned_worker_slug == AssignedWorkerSlug(failing_leaf)
    assert spec.depends_on == [TaskSlug("l_1")]

    for slug in ("d_root", "d_left", "d_right", "d_join", "l_1", "l_3", "s_a", "s_b"):
        spec = worker._spec_for(slug, (), "…")
        assert spec.assigned_worker_slug == AssignedWorkerSlug(happy_leaf), (
            f"{slug} should use happy leaf, got {spec.assigned_worker_slug}"
        )


@pytest.mark.parametrize(
    "worker_cls",
    [ResearchRubricsSadPathSmokeWorker, MiniF2FSadPathSmokeWorker, SweBenchSadPathSmokeWorker],
)
def test_only_l_2_is_in_failing_slugs(worker_cls) -> None:
    """Sanity: future additions to FAILING_SLUGS should be conscious.
    If this assertion tightens, the sad-path driver's invariants must
    be updated in lock-step (8 messages vs 7, partial count, etc.)."""
    assert worker_cls.FAILING_SLUGS == frozenset({"l_2"})
