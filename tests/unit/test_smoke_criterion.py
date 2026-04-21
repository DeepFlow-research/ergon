"""SmokeCriterionBase: structural + probe checks via DB lookups.

All DB-pulling methods on the base class are monkeypatched in these tests
so the unit tests stay self-contained. Integration-level coverage (real
Postgres, real RunResources) lives in the PR 2+ pytest suite.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from ergon_builtins.evaluators.criteria.smoke_criterion import SmokeCriterionBase
from ergon_builtins.workers.stubs.canonical_smoke_worker import EXPECTED_SUBTASK_SLUGS


def _healthy_children() -> list[SimpleNamespace]:
    return [
        SimpleNamespace(task_slug=s, status="completed", id=uuid4()) for s in EXPECTED_SUBTASK_SLUGS
    ]


def _healthy_probes() -> dict[UUID, dict]:
    return {}  # override per test via the pulled-children list


class _PassthroughCriterion(SmokeCriterionBase):
    type_slug = "smoke-passthrough-test"

    async def _verify_env_content(self, context, children, probes) -> None:  # noqa: ANN001
        return


def _patched(crit, children, probes_by_child_id):
    crit._pull_children = AsyncMock(return_value=children)
    crit._pull_probe_results = AsyncMock(return_value=probes_by_child_id)
    return crit


def _eval_context() -> SimpleNamespace:
    return SimpleNamespace(
        run_id=uuid4(),
        task_id=uuid4(),
        execution_id=uuid4(),
        task=None,
        worker_result=None,
        sandbox_id="sb",
        metadata={},
        runtime=None,
    )


@pytest.mark.asyncio
async def test_passes_with_canonical_graph_and_probes() -> None:
    children = _healthy_children()
    probes = {c.id: {"exit_code": 0, "stdout": "ok"} for c in children}
    crit = _patched(_PassthroughCriterion(name="smoke"), children, probes)
    result = await crit.evaluate(_eval_context())
    assert result.passed is True and result.score == 1.0


@pytest.mark.asyncio
async def test_fails_when_graph_shape_differs() -> None:
    children = _healthy_children()[:-1]  # drop s_b
    probes = {c.id: {"exit_code": 0, "stdout": "ok"} for c in children}
    crit = _patched(_PassthroughCriterion(name="smoke"), children, probes)
    result = await crit.evaluate(_eval_context())
    assert result.passed is False
    assert "graph shape" in (result.feedback or "").lower()


@pytest.mark.asyncio
async def test_fails_when_child_not_completed() -> None:
    children = _healthy_children()
    children[0].status = "failed"
    probes = {c.id: {"exit_code": 0, "stdout": "ok"} for c in children}
    crit = _patched(_PassthroughCriterion(name="smoke"), children, probes)
    result = await crit.evaluate(_eval_context())
    assert result.passed is False
    assert "not completed" in (result.feedback or "").lower()


@pytest.mark.asyncio
async def test_fails_when_probe_exit_nonzero() -> None:
    children = _healthy_children()
    probes = {c.id: {"exit_code": 0, "stdout": "ok"} for c in children}
    probes[children[0].id] = {"exit_code": 1, "stdout": "boom"}
    crit = _patched(_PassthroughCriterion(name="smoke"), children, probes)
    result = await crit.evaluate(_eval_context())
    assert result.passed is False
    assert "probe" in (result.feedback or "").lower()


@pytest.mark.asyncio
async def test_verify_env_content_is_abstract_default() -> None:
    class Subclass(SmokeCriterionBase):
        type_slug = "smoke-abstract-test"

    crit = _patched(Subclass(name="smoke"), _healthy_children(), {})
    # _verify_env_content is called after structural checks pass; the default raises.
    with pytest.raises(NotImplementedError):
        await crit.evaluate(_eval_context())


@pytest.mark.asyncio
async def test_fails_gracefully_when_puller_raises_unexpected_error() -> None:
    crit = _patched(_PassthroughCriterion(name="smoke"), _healthy_children(), {})
    crit._pull_children = AsyncMock(side_effect=RuntimeError("db connection closed"))
    result = await crit.evaluate(_eval_context())
    assert result.passed is False
    assert result.score == 0.0
    assert "errored" in (result.feedback or "").lower()
    assert "RuntimeError" in (result.feedback or "")
    assert "db connection closed" in (result.feedback or "")
