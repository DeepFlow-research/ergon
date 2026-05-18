from uuid import uuid4

import pytest

from ergon_core.test_support.task_factory import task_with_id


def test_worker_task_carries_runtime_graph_node_identity() -> None:
    node_id = uuid4()
    task = task_with_id(
        node_id,
        task_slug="root",
        instance_key="default",
        description="Runtime task",
    )

    assert task.task_id == node_id


def test_worker_task_without_runtime_identity_raises_on_read() -> None:
    task = task_with_id(
        uuid4(),
        task_slug="root",
        instance_key="default",
        description="Runtime task",
    )
    task._task_id = None
    with pytest.raises(RuntimeError, match="task_id"):
        _ = task.task_id
