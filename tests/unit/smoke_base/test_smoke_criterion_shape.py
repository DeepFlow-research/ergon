"""``SmokeCriterionBase._check_graph_shape`` rejects slug-set mismatches.

Pure: constructs fake ``RunGraphNode``-shaped values (only ``task_slug``
is read) and asserts error behaviour.
"""

from dataclasses import dataclass

import pytest

from ergon_core.api.errors import CriteriaCheckError
from tests.e2e._fixtures.smoke_base.constants import EXPECTED_SUBTASK_SLUGS
from tests.e2e._fixtures.smoke_base.criterion_base import SmokeCriterionBase


@dataclass
class _FakeNode:
    task_slug: str


class _Crit(SmokeCriterionBase):
    type_slug = "unit-test-criterion-shape"

    async def _verify_env_content(self, context, children, probes):  # pragma: no cover
        pass

    async def _verify_sandbox_setup(self, context):  # pragma: no cover
        pass


def _crit() -> _Crit:
    return _Crit(name="unit-test")


def test_correct_slug_set_passes() -> None:
    children = [_FakeNode(task_slug=s) for s in EXPECTED_SUBTASK_SLUGS]
    # Should not raise.
    _crit()._check_graph_shape(children)  # type: ignore[arg-type]


def test_missing_slug_raises() -> None:
    missing_l_3 = [s for s in EXPECTED_SUBTASK_SLUGS if s != "l_3"]
    children = [_FakeNode(task_slug=s) for s in missing_l_3]
    with pytest.raises(CriteriaCheckError, match="graph shape mismatch"):
        _crit()._check_graph_shape(children)  # type: ignore[arg-type]


def test_extra_slug_raises() -> None:
    children = [_FakeNode(task_slug=s) for s in EXPECTED_SUBTASK_SLUGS]
    children.append(_FakeNode(task_slug="unexpected_extra"))
    with pytest.raises(CriteriaCheckError, match="graph shape mismatch"):
        _crit()._check_graph_shape(children)  # type: ignore[arg-type]


def test_renamed_slug_raises() -> None:
    renamed = [
        _FakeNode(task_slug=(s if s != "d_join" else "d_joined")) for s in EXPECTED_SUBTASK_SLUGS
    ]
    with pytest.raises(CriteriaCheckError, match="graph shape mismatch"):
        _crit()._check_graph_shape(renamed)  # type: ignore[arg-type]
