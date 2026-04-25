"""``SmokeCriterionBase._check_probes_succeeded`` rejects non-zero probe exits."""

from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest

from ergon_core.api.errors import CriteriaCheckError
from tests.e2e._fixtures.smoke_base.criterion_base import SmokeCriterionBase


@dataclass
class _FakeNode:
    id: UUID
    task_slug: str


class _Crit(SmokeCriterionBase):
    type_slug = "unit-test-criterion-probe"

    async def _verify_env_content(self, context, children, probes):  # pragma: no cover
        pass

    async def _verify_sandbox_setup(self, context):  # pragma: no cover
        pass


def _crit() -> _Crit:
    return _Crit(name="unit-test")


def test_all_zero_exits_passes() -> None:
    c1, c2 = _FakeNode(uuid4(), "a"), _FakeNode(uuid4(), "b")
    probes = {
        c1.id: {"exit_code": 0, "stdout": "ok"},
        c2.id: {"exit_code": 0, "stdout": "ok"},
    }
    _crit()._check_probes_succeeded(probes, [c1, c2])  # type: ignore[arg-type]


def test_non_zero_exit_raises_with_slug() -> None:
    c1 = _FakeNode(uuid4(), "l_2")
    c2 = _FakeNode(uuid4(), "d_root")
    probes = {
        c1.id: {"exit_code": 1, "stdout": "boom"},
        c2.id: {"exit_code": 0, "stdout": "ok"},
    }
    with pytest.raises(CriteriaCheckError, match=r"l_2.*exited 1.*boom"):
        _crit()._check_probes_succeeded(probes, [c1, c2])  # type: ignore[arg-type]


def test_missing_exit_code_raises() -> None:
    c1 = _FakeNode(uuid4(), "d_root")
    probes = {c1.id: {"stdout": "no exit_code"}}
    with pytest.raises(CriteriaCheckError, match="d_root.*exited None"):
        _crit()._check_probes_succeeded(probes, [c1])  # type: ignore[arg-type]


def test_unknown_child_id_uses_uuid_string() -> None:
    """Probe dict may have a node id not in children (shouldn't happen in
    practice, but defensive formatting keeps the error legible)."""
    orphan_id = uuid4()
    probes = {orphan_id: {"exit_code": 2, "stdout": "x"}}
    with pytest.raises(CriteriaCheckError, match=r"exited 2"):
        _crit()._check_probes_succeeded(probes, [])  # type: ignore[arg-type]
