from uuid import uuid4

import pytest

from ergon_core.core.persistence.shared.types import AssignedWorkerSlug, TaskSlug
from ergon_core.test_support.smoke_fixtures.workers.minif2f_smoke import MiniF2FSmokeWorker
from ergon_core.test_support.smoke_fixtures.workers.researchrubrics_smoke import (
    ResearchRubricsSmokeWorker,
)
from ergon_core.test_support.smoke_fixtures.workers.swebench_smoke import SweBenchSmokeWorker


@pytest.mark.parametrize(
    ("worker_cls", "happy_leaf", "recursive_worker"),
    [
        (
            ResearchRubricsSmokeWorker,
            "researchrubrics-smoke-leaf",
            "researchrubrics-smoke-recursive-worker",
        ),
        (MiniF2FSmokeWorker, "minif2f-smoke-leaf", "minif2f-smoke-recursive-worker"),
        (SweBenchSmokeWorker, "swebench-smoke-leaf", "swebench-smoke-recursive-worker"),
    ],
)
def test_happy_l_2_routes_to_recursive_worker(
    worker_cls,
    happy_leaf: str,
    recursive_worker: str,
) -> None:
    worker = worker_cls(
        name="unit-test",
        model=None,
        task_id=uuid4(),
        sandbox_id="sbx-unit",
    )

    spec = worker._spec_for("l_2", ("l_1",), "Line 2")
    assert spec.task_slug == TaskSlug("l_2")
    assert spec.assigned_worker_slug == AssignedWorkerSlug(recursive_worker)
    assert spec.depends_on == [TaskSlug("l_1")]

    for slug in ("d_root", "d_left", "d_right", "d_join", "l_1", "l_3", "s_a", "s_b"):
        spec = worker._spec_for(slug, (), "...")
        assert spec.assigned_worker_slug == AssignedWorkerSlug(happy_leaf), (
            f"{slug} should use happy leaf, got {spec.assigned_worker_slug}"
        )
