from uuid import uuid4

import pytest

from ergon_core.api.benchmark import EmptyTaskPayload, Task, TaskSpec
from ergon_core.test_support.task_factory import task_with_id


def test_task_spec_is_definition_time_and_has_no_runtime_id() -> None:
    spec = TaskSpec(
        task_slug="root",
        instance_key="default",
        description="Definition-time task",
        task_payload=EmptyTaskPayload(),
    )

    assert spec.task_slug == "root"
    assert not hasattr(spec, "task_id")


def test_worker_task_carries_runtime_graph_node_identity() -> None:
    """PR 2 contract: `task_id` is a PrivateAttr exposed via the
    `task_id` property; binding happens through `from_definition` or
    the `task_with_id` test helper."""

    node_id = uuid4()
    task = task_with_id(
        node_id,
        task_slug="root",
        instance_key="default",
        description="Runtime task",
    )

    assert task.task_id == node_id


def test_worker_task_without_runtime_identity_raises_on_read() -> None:
    """PR 2 contract: constructing a Task without binding `_task_id`
    succeeds, but reading `task.task_id` raises — the bug surfaces at
    the boundary, not silently later."""

    task = Task(
        task_slug="root",
        instance_key="default",
        description="Runtime task",
    )
    with pytest.raises(RuntimeError, match="task_id"):
        _ = task.task_id
