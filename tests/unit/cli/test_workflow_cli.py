import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from ergon_cli.commands.workflow import WorkflowCommandContext, execute_workflow_command
from ergon_core.core.runtime.services.workflow_dto import (
    WorkflowExecutionRef,
    WorkflowMutationRef,
    WorkflowResourceLocationRef,
    WorkflowResourceRef,
    WorkflowTaskRef,
    WorkflowTaskWorkspaceRef,
)
from pydantic import BaseModel


class _Session:
    def close(self) -> None:
        pass


class _Service(BaseModel):
    model_config = {"arbitrary_types_allowed": True}

    resource: WorkflowResourceRef | None

    def list_resources(self, session, *, run_id, node_id, scope, kind=None, max_depth=3, limit=50):
        assert isinstance(session, _Session)
        assert self.resource is not None
        assert run_id == self.resource.run_id
        assert node_id == self.resource.node_id
        assert scope == "visible"
        assert kind is None
        assert max_depth == 3
        assert limit == 5
        return [self.resource]


def test_resource_list_json_uses_injected_context() -> None:
    run_id = uuid4()
    node_id = uuid4()
    resource = WorkflowResourceRef(
        resource_id=uuid4(),
        run_id=run_id,
        task_execution_id=uuid4(),
        node_id=node_id,
        task_slug="research",
        kind="report",
        name="paper.txt",
        mime_type="text/plain",
        size_bytes=12,
        file_path="/tmp/paper.txt",
        content_hash="sha256:abc",
        copied_from_resource_id=None,
        created_at=datetime(2026, 4, 26, tzinfo=UTC),
    )
    output = execute_workflow_command(
        "inspect resource-list --scope visible --limit 5 --format json",
        context=WorkflowCommandContext(
            run_id=run_id,
            node_id=node_id,
            execution_id=uuid4(),
            sandbox_task_key=uuid4(),
            benchmark_type="researchrubrics",
        ),
        session_factory=_Session,
        service=_Service(resource=resource),
    )

    payload = json.loads(output.stdout)

    assert output.exit_code == 0
    assert payload["resources"][0]["name"] == "paper.txt"
    assert payload["resources"][0]["task_slug"] == "research"


def test_manage_add_task_json_plumbs_cli_arguments_to_service() -> None:
    expected_run_id = uuid4()
    expected_parent_node_id = uuid4()
    created_node_id = uuid4()

    class Service:
        async def add_task(
            self,
            session,
            *,
            run_id,
            parent_node_id,
            task_slug,
            description,
            assigned_worker_slug,
            dry_run,
        ):
            assert isinstance(session, _Session)
            assert run_id == expected_run_id
            assert parent_node_id == expected_parent_node_id
            assert task_slug == "new_leaf"
            assert description == "New leaf"
            assert assigned_worker_slug == "researchrubrics-researcher"
            assert dry_run is True
            return WorkflowMutationRef(
                action="add-task",
                dry_run=True,
                node=WorkflowTaskRef(
                    node_id=created_node_id,
                    task_slug="new_leaf",
                    status="pending",
                    level=2,
                    parent_node_id=expected_parent_node_id,
                    assigned_worker_slug="researchrubrics-researcher",
                    description="New leaf",
                ),
                message="Would add task new_leaf",
            )

    output = execute_workflow_command(
        "manage add-task --task-slug new_leaf --description 'New leaf' "
        "--worker researchrubrics-researcher "
        f"--parent-node-id {expected_parent_node_id} --dry-run --format json",
        context=WorkflowCommandContext(
            run_id=expected_run_id,
            node_id=expected_parent_node_id,
            execution_id=uuid4(),
            sandbox_task_key=uuid4(),
            benchmark_type="researchrubrics",
        ),
        session_factory=_Session,
        service=Service(),
    )

    payload = json.loads(output.stdout)
    assert payload["mutation"]["action"] == "add-task"
    assert payload["mutation"]["node"]["task_slug"] == "new_leaf"
    assert payload["mutation"]["dry_run"] is True


def test_resource_location_json_uses_injected_run_scope() -> None:
    run_id = uuid4()
    node_id = uuid4()
    resource_id = uuid4()
    resource = WorkflowResourceRef(
        resource_id=resource_id,
        run_id=run_id,
        task_execution_id=uuid4(),
        node_id=node_id,
        task_slug="producer",
        kind="report",
        name="paper.txt",
        mime_type="text/plain",
        size_bytes=12,
        file_path="/tmp/paper.txt",
        content_hash="sha256:abc",
        copied_from_resource_id=None,
        created_at=datetime(2026, 4, 26, tzinfo=UTC),
    )

    class Service:
        def get_resource_location(self, session, *, run_id, resource_id):
            assert isinstance(session, _Session)
            assert run_id == resource.run_id
            assert resource_id == resource.resource_id
            return WorkflowResourceLocationRef(
                resource=resource,
                producer_task_slug="producer",
                local_file_path="/tmp/paper.txt",
                default_sandbox_path="/workspace/imported/producer/paper (copy).txt",
            )

    output = execute_workflow_command(
        f"inspect resource-location --resource-id {resource_id} --format json",
        context=WorkflowCommandContext(
            run_id=run_id,
            node_id=node_id,
            execution_id=uuid4(),
            sandbox_task_key=uuid4(),
            benchmark_type="researchrubrics",
        ),
        session_factory=_Session,
        service=Service(),
    )

    payload = json.loads(output.stdout)
    assert payload["resource_location"]["producer_task_slug"] == "producer"
    assert payload["resource_location"]["default_sandbox_path"].startswith("/workspace/imported")


def test_task_workspace_text_lists_own_and_input_resources() -> None:
    run_id = uuid4()
    node_id = uuid4()
    execution_id = uuid4()

    class Service:
        def get_task_workspace(self, session, *, run_id, node_id):
            assert isinstance(session, _Session)
            return WorkflowTaskWorkspaceRef(
                task=WorkflowTaskRef(
                    node_id=node_id,
                    task_slug="current",
                    status="running",
                    level=1,
                    description="Current",
                ),
                latest_execution=WorkflowExecutionRef(
                    execution_id=execution_id,
                    status="running",
                    attempt_number=1,
                    final_assistant_message=None,
                ),
                own_resources=[
                    WorkflowResourceRef(
                        resource_id=uuid4(),
                        run_id=run_id,
                        task_execution_id=execution_id,
                        node_id=node_id,
                        task_slug="current",
                        kind="report",
                        name="own.txt",
                        mime_type="text/plain",
                        size_bytes=3,
                        file_path="/tmp/own.txt",
                        created_at=datetime(2026, 4, 26, tzinfo=UTC),
                    )
                ],
                input_resources=[
                    WorkflowResourceRef(
                        resource_id=uuid4(),
                        run_id=run_id,
                        task_execution_id=uuid4(),
                        node_id=uuid4(),
                        task_slug="upstream",
                        kind="report",
                        name="input.txt",
                        mime_type="text/plain",
                        size_bytes=5,
                        file_path="/tmp/input.txt",
                        created_at=datetime(2026, 4, 26, tzinfo=UTC),
                    )
                ],
            )

    output = execute_workflow_command(
        "inspect task-workspace",
        context=WorkflowCommandContext(
            run_id=run_id,
            node_id=node_id,
            execution_id=execution_id,
            sandbox_task_key=uuid4(),
            benchmark_type="researchrubrics",
        ),
        session_factory=_Session,
        service=Service(),
    )

    assert "task current status=running" in output.stdout
    assert "own: own.txt" in output.stdout
    assert "input: input.txt" in output.stdout


def test_agent_command_rejects_user_supplied_context_flags() -> None:
    with pytest.raises(ValueError, match="scope/context flags are injected"):
        execute_workflow_command(
            f"inspect resource-list --scope visible --run-id {uuid4()}",
            context=WorkflowCommandContext(
                run_id=uuid4(),
                node_id=uuid4(),
                execution_id=uuid4(),
                sandbox_task_key=uuid4(),
                benchmark_type="researchrubrics",
            ),
            session_factory=_Session,
            service=_Service(resource=None),  # type: ignore[arg-type]
        )
