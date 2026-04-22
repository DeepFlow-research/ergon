"""CanonicalSmokeWorker: plans a hardcoded 9-node DAG via plan_subtasks."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from ergon_builtins.workers.stubs.canonical_smoke_worker import (
    EXPECTED_SUBTASK_SLUGS,
    CanonicalSmokeWorker,
)


def test_expected_slugs_constant_shape() -> None:
    assert EXPECTED_SUBTASK_SLUGS == (
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
    assert len(EXPECTED_SUBTASK_SLUGS) == 9
    assert len(set(EXPECTED_SUBTASK_SLUGS)) == 9


@pytest.mark.asyncio
async def test_execute_calls_plan_subtasks_with_correct_topology() -> None:
    captured_command = {}

    async def fake_plan_subtasks(session, command):
        captured_command["cmd"] = command
        nodes = {spec.task_slug: uuid4() for spec in command.subtasks}
        roots = [spec.task_slug for spec in command.subtasks if not spec.depends_on]
        return SimpleNamespace(nodes=nodes, roots=roots)

    fake_service = MagicMock()
    fake_service.plan_subtasks = AsyncMock(side_effect=fake_plan_subtasks)

    class _DummySessionCtx:
        def __enter__(self):
            return MagicMock()

        def __exit__(self, *a):
            return False

    with (
        patch(
            "ergon_builtins.workers.stubs.canonical_smoke_worker.TaskManagementService",
            return_value=fake_service,
        ),
        patch(
            "ergon_builtins.workers.stubs.canonical_smoke_worker.get_session",
            return_value=_DummySessionCtx(),
        ),
    ):
        parent_node = UUID("00000000-0000-0000-0000-00000000dead")
        ctx = SimpleNamespace(
            run_id=uuid4(),
            definition_id=None,
            task_id=uuid4(),
            execution_id=uuid4(),
            sandbox_id="sb",
            node_id=parent_node,
            metadata={},
        )
        worker = CanonicalSmokeWorker(name="smoke", model=None)
        turns = [t async for t in worker.execute(task=None, context=ctx)]

    assert len(turns) >= 1
    cmd = captured_command["cmd"]
    assert cmd.parent_node_id == parent_node
    slugs = {s.task_slug: s for s in cmd.subtasks}
    assert set(slugs) == set(EXPECTED_SUBTASK_SLUGS)
    assert slugs["d_root"].depends_on == []
    assert slugs["d_left"].depends_on == ["d_root"]
    assert slugs["d_right"].depends_on == ["d_root"]
    assert sorted(slugs["d_join"].depends_on) == ["d_left", "d_right"]
    assert slugs["l_1"].depends_on == []
    assert slugs["l_2"].depends_on == ["l_1"]
    assert slugs["l_3"].depends_on == ["l_2"]
    assert slugs["s_a"].depends_on == []
    assert slugs["s_b"].depends_on == []
    for spec in cmd.subtasks:
        assert spec.assigned_worker_slug == "smoke-leaf"
