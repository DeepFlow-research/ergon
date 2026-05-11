from uuid import uuid4

import pytest
from pydantic import ValidationError

from ergon_core.api.benchmark import EmptyTaskPayload, Task, TaskSpec


def test_task_spec_is_definition_time_and_has_no_runtime_id() -> None:
    spec = TaskSpec(
        task_slug="root",
        instance_key="default",
        description="Definition-time task",
        task_payload=EmptyTaskPayload(),
    )

    assert spec.task_slug == "root"
    assert not hasattr(spec, "task_id")


def test_worker_task_requires_runtime_graph_node_identity() -> None:
    node_id = uuid4()

    task = Task(
        task_id=node_id,
        task_slug="root",
        instance_key="default",
        description="Runtime task",
    )

    assert task.task_id == node_id


def test_worker_task_rejects_missing_runtime_identity() -> None:
    with pytest.raises(ValidationError, match="task_id"):
        Task(
            task_slug="root",
            instance_key="default",
            description="Runtime task",
        )
