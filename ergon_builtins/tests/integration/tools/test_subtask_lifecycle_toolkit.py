from uuid import uuid4

import pytest

from ergon_builtins.tools.subtask_lifecycle_toolkit import (
    SubtaskLifecycleToolkit,
    ToolFailure,
)


@pytest.mark.asyncio
async def test_subtask_lifecycle_toolkit_spawns_dynamic_object_bound_child(
    toy_workflow_harness,
) -> None:
    toolkit = SubtaskLifecycleToolkit(context=toy_workflow_harness.context)
    spawn_task = next(tool for tool in toolkit.get_tools() if tool.__name__ == "spawn_task")
    task = toy_workflow_harness.child_task(task_slug="typed-child", description="Typed child")

    result = await spawn_task(task)
    child = next(node for node in toy_workflow_harness.nodes() if node.task_slug == "typed-child")

    assert result.kind == "success"
    assert result.task_id == child.task_id
    assert child.is_dynamic is True
    assert child.task_json["task_slug"] == "typed-child"
    assert child.task_json["worker"]["_type"].endswith(":ToyWorker")
    assert toy_workflow_harness.definition_tasks() == []


@pytest.mark.asyncio
async def test_non_descendant_lifecycle_mutation_is_blocked(
    toy_workflow_harness,
) -> None:
    toolkit = SubtaskLifecycleToolkit(context=toy_workflow_harness.context)
    cancel_task = next(tool for tool in toolkit.get_tools() if tool.__name__ == "cancel_task")

    result = await cancel_task(str(uuid4()))

    assert isinstance(result, ToolFailure)
    assert result.kind == "failure"
    assert "not a descendant" in result.error.lower()
