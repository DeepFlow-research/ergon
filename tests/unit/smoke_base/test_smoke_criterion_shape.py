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


def _nodes_missing_slug() -> list[_FakeNode]:
    return [_FakeNode(task_slug=s) for s in EXPECTED_SUBTASK_SLUGS if s != "l_3"]


def _nodes_extra_slug() -> list[_FakeNode]:
    nodes = [_FakeNode(task_slug=s) for s in EXPECTED_SUBTASK_SLUGS]
    nodes.append(_FakeNode(task_slug="unexpected_extra"))
    return nodes


def _nodes_renamed_slug() -> list[_FakeNode]:
    return [
        _FakeNode(task_slug=(s if s != "d_join" else "d_joined")) for s in EXPECTED_SUBTASK_SLUGS
    ]


@pytest.mark.parametrize(
    "children",
    [
        pytest.param(_nodes_missing_slug(), id="missing_slug"),
        pytest.param(_nodes_extra_slug(), id="extra_slug"),
        pytest.param(_nodes_renamed_slug(), id="renamed_slug"),
    ],
)
def test_bad_slug_set_raises(children: list[_FakeNode]) -> None:
    with pytest.raises(CriteriaCheckError, match="graph shape mismatch"):
        _crit()._check_graph_shape(children)  # type: ignore[arg-type]
