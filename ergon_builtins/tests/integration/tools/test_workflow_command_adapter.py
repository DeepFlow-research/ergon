import json
from uuid import uuid4

import pytest

from ergon_builtins.tools.workflow_cli_tool import make_workflow_cli_tool
from ergon_builtins.tools.workflow_command_adapter import (
    WorkflowCommandContext,
    execute_workflow_command,
)
from ergon_core.api import Task


def _command_context(harness) -> WorkflowCommandContext:
    return WorkflowCommandContext(
        run_id=harness.context.run_id,
        task_id=harness.context.task_id,
        execution_id=harness.context.execution_id,
        sandbox_task_key=harness.context.task_id,
        benchmark_type="toy",
    )


@pytest.mark.asyncio
async def test_toy_task_round_trips_through_task_definition(
    toy_workflow_harness,
) -> None:
    task = toy_workflow_harness.child_task(task_slug="child", description="Child task")

    inflated = await Task.from_definition(
        task.model_dump(mode="json"),
        task_id=uuid4(),
    )

    assert inflated.task_slug == "child"
    assert inflated.worker.type_slug == "toy-worker"
    assert inflated.sandbox.type_slug == "toy-sandbox"


@pytest.mark.asyncio
async def test_workflow_command_spawns_dynamic_object_bound_child(
    toy_workflow_harness,
) -> None:
    output = await execute_workflow_command(
        "manage add-subtask --task-slug child --description 'Child task' --format json",
        context=_command_context(toy_workflow_harness),
        worker_context=toy_workflow_harness.context,
        session_factory=toy_workflow_harness.context.session_factory,
    )

    payload = json.loads(output.stdout)
    child_id = payload["spawned_task"]["task_id"]
    child = next(node for node in toy_workflow_harness.nodes() if str(node.task_id) == child_id)

    assert output.exit_code == 0
    assert child.is_dynamic is True
    assert child.task_slug == "child"
    assert child.parent_task_id == toy_workflow_harness.parent_task_id
    assert child.task_json["task_slug"] == "child"
    assert child.task_json["description"] == "Child task"
    assert child.task_json["_type"].endswith(":Task")
    assert child.task_json["worker"]["_type"].endswith(":ToyWorker")
    assert child.task_json["sandbox"]["_type"].endswith(":ToySandbox")
    assert toy_workflow_harness.definition_tasks() == []


@pytest.mark.asyncio
async def test_agent_workflow_tool_spawns_dynamic_object_bound_child(
    toy_workflow_harness,
) -> None:
    workflow = make_workflow_cli_tool(
        worker_context=toy_workflow_harness.context,
        sandbox_task_key=toy_workflow_harness.context.task_id,
        benchmark_type="toy",
        session_factory=toy_workflow_harness.context.session_factory,
    )

    stdout = await workflow(
        "manage add-subtask --task-slug tool-child --description 'Tool child' --format json"
    )

    child_id = json.loads(stdout)["spawned_task"]["task_id"]
    child = next(node for node in toy_workflow_harness.nodes() if str(node.task_id) == child_id)

    assert child.is_dynamic is True
    assert child.task_slug == "tool-child"
    assert child.task_json["worker"]["_type"].endswith(":ToyWorker")
    assert toy_workflow_harness.definition_tasks() == []


@pytest.mark.asyncio
async def test_workflow_command_writes_dependency_edge_through_core(
    toy_workflow_harness,
) -> None:
    dependency = next(
        node for node in toy_workflow_harness.nodes() if node.task_slug == "dependency"
    )

    output = await execute_workflow_command(
        "manage add-subtask --task-slug child --description 'Child task' "
        f"--depends-on {dependency.task_id} --format json",
        context=_command_context(toy_workflow_harness),
        worker_context=toy_workflow_harness.context,
        session_factory=toy_workflow_harness.context.session_factory,
    )

    child_id = json.loads(output.stdout)["spawned_task"]["task_id"]
    edges = toy_workflow_harness.edges()

    assert output.exit_code == 0
    assert len(edges) == 1
    assert edges[0].source_task_id == dependency.task_id
    assert str(edges[0].target_task_id) == child_id


@pytest.mark.asyncio
async def test_workflow_command_rejects_unknown_dependency_without_partial_write(
    toy_workflow_harness,
) -> None:
    node_ids_before = {node.task_id for node in toy_workflow_harness.nodes()}
    edge_ids_before = {edge.id for edge in toy_workflow_harness.edges()}

    output = await execute_workflow_command(
        "manage add-subtask --task-slug child --description 'Child task' "
        f"--depends-on {uuid4()} --format json",
        context=_command_context(toy_workflow_harness),
        worker_context=toy_workflow_harness.context,
        session_factory=toy_workflow_harness.context.session_factory,
    )

    assert output.exit_code == 2
    assert output.stderr is not None
    assert "missing node" in output.stderr
    assert {node.task_id for node in toy_workflow_harness.nodes()} == node_ids_before
    assert {edge.id for edge in toy_workflow_harness.edges()} == edge_ids_before


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "flag",
    [
        "--run-id",
        "--task-id",
        "--node-id",
        "--execution-id",
        "--sandbox-id",
        "--sandbox-task-key",
        "--benchmark-type",
    ],
)
async def test_context_escape_flags_are_rejected(
    toy_workflow_harness,
    flag: str,
) -> None:
    output = await execute_workflow_command(
        f"manage add-subtask --task-slug child --description child {flag} {uuid4()}",
        context=_command_context(toy_workflow_harness),
        worker_context=toy_workflow_harness.context,
        session_factory=toy_workflow_harness.context.session_factory,
    )

    assert output.exit_code == 2
    assert output.stderr is not None
    assert "scope/context flags are injected" in output.stderr
    assert [node for node in toy_workflow_harness.nodes() if node.task_slug == "child"] == []


@pytest.mark.asyncio
async def test_context_escape_flags_are_rejected_before_session_open(
    toy_workflow_harness,
) -> None:
    def fail_if_opened():
        raise AssertionError("session should not be opened")

    output = await execute_workflow_command(
        f"inspect task-tree --run-id {uuid4()}",
        context=_command_context(toy_workflow_harness),
        worker_context=toy_workflow_harness.context,
        session_factory=fail_if_opened,
    )

    assert output.exit_code == 2
    assert output.stderr is not None
    assert "scope/context flags are injected" in output.stderr


@pytest.mark.asyncio
async def test_slug_only_dynamic_authoring_is_rejected(
    toy_workflow_harness,
) -> None:
    output = await execute_workflow_command(
        "manage add-subtask --task-slug child",
        context=_command_context(toy_workflow_harness),
        worker_context=toy_workflow_harness.context,
        session_factory=toy_workflow_harness.context.session_factory,
    )

    assert output.exit_code == 2
    assert output.stderr is not None
    assert "--description" in output.stderr
    assert [node for node in toy_workflow_harness.nodes() if node.task_slug == "child"] == []
