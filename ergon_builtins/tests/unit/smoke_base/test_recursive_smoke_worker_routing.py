import pytest
from ergon_core.core.persistence.shared.types import TaskSlug
from tests.fixtures.smoke_components.workers.minif2f_smoke import MiniF2FSmokeWorker
from tests.fixtures.smoke_components.workers.researchrubrics_smoke import (
    ResearchRubricsSmokeWorker,
)
from tests.fixtures.smoke_components.workers.swebench_smoke import SweBenchSmokeWorker


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
    )

    spec = worker._spec_for("l_2", ("l_1",), "Line 2")
    assert spec.task.task_slug == TaskSlug("l_2")
    assert spec.task.worker.name == recursive_worker
    assert spec.depends_on == [TaskSlug("l_1")]

    for slug in ("d_root", "d_left", "d_right", "d_join", "l_1", "l_3", "s_a", "s_b"):
        spec = worker._spec_for(slug, (), "...")
        assert spec.task.worker.name == happy_leaf, (
            f"{slug} should use happy leaf, got {spec.task.worker.name}"
        )
