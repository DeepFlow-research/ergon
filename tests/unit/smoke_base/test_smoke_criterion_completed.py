"""``SmokeCriterionBase._check_children_completed`` rejects non-terminal children."""

import pytest
from pydantic import BaseModel

from ergon_core.api.errors import CriteriaCheckError
from ergon_core.core.persistence.graph.status_conventions import COMPLETED
from ergon_core.test_support.smoke_fixtures.smoke_base.criterion_base import SmokeCriterionBase


class _FakeNode(BaseModel):
    model_config = {"frozen": True}

    task_slug: str
    status: str


class _Crit(SmokeCriterionBase):
    type_slug = "unit-test-criterion-completed"

    async def _verify_env_content(self, context, children, probes):  # pragma: no cover
        pass

    async def _verify_sandbox_setup(self, context):  # pragma: no cover
        pass


def _crit() -> _Crit:
    return _Crit(name="unit-test")


def test_all_completed_passes() -> None:
    children = [_FakeNode(task_slug=f"l_{i}", status=COMPLETED) for i in range(3)]
    _crit()._check_children_completed(children)


def test_any_non_completed_raises() -> None:
    children = [
        _FakeNode(task_slug="d_root", status=COMPLETED),
        _FakeNode(task_slug="d_left", status=COMPLETED),
        _FakeNode(task_slug="d_right", status="in_progress"),
    ]
    with pytest.raises(CriteriaCheckError, match="d_right not completed"):
        _crit()._check_children_completed(children)


def test_failed_child_raises_with_slug() -> None:
    """Sad-path shape: ``l_2`` status == FAILED surfaces with slug named."""
    children = [
        _FakeNode(task_slug="l_1", status=COMPLETED),
        _FakeNode(task_slug="l_2", status="failed"),
        _FakeNode(task_slug="l_3", status="blocked"),
    ]
    with pytest.raises(CriteriaCheckError, match="l_2 not completed"):
        _crit()._check_children_completed(children)


def test_empty_children_passes() -> None:
    """No children ⇒ vacuously true.  Empty-check is the caller's job
    (``_check_graph_shape`` catches it before this method runs)."""
    _crit()._check_children_completed([])
