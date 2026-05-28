import json
from datetime import UTC, datetime
from uuid import uuid4

from ergon_cli.domains.workflow.executor import execute_workflow_command
from ergon_cli.domains.workflow.models import WorkflowCommandContext
from ergon_core.core.application.runtime.models import GraphTaskRef
from ergon_core.core.application.runtime.workflow_models import WorkflowResourceRef
from pydantic import BaseModel, ConfigDict


class _Session:
    def close(self) -> None:
        pass


class _Service(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    resource: WorkflowResourceRef | None

    def list_resources(
        self, session, *, sample_id, task_id, scope, kind=None, max_depth=3, limit=50
    ):
        assert isinstance(session, _Session)
        assert self.resource is not None
        assert sample_id == self.resource.sample_id
        assert task_id == self.resource.task_id
        assert scope == "visible"
        assert kind is None
        assert max_depth == 3
        assert limit == 5
        return [self.resource]


class _TaskTreeService(BaseModel):
    requested_parent_task_id: object | None = None

    def list_tasks(self, session, *, sample_id, parent_task_id=None):
        assert isinstance(session, _Session)
        self.requested_parent_task_id = parent_task_id
        return [
            GraphTaskRef(
                task_id=uuid4(),
                task_slug="child",
                status="pending",
                level=1,
                parent_task_id=parent_task_id,
                assigned_worker_slug="react-v1",
                description="Child task",
            )
        ]


class _FailingService:
    def list_resources(self, *args, **kwargs):
        raise ValueError("unsupported resource scope: all")


def _context() -> WorkflowCommandContext:
    return WorkflowCommandContext(
        sample_id=uuid4(),
        task_id=uuid4(),
        execution_id=uuid4(),
        sandbox_task_key=uuid4(),
        benchmark_type="researchrubrics",
    )


def test_resource_list_json_uses_injected_context() -> None:
    sample_id = uuid4()
    task_id = uuid4()
    resource = WorkflowResourceRef(
        resource_id=uuid4(),
        sample_id=sample_id,
        task_attempt_id=uuid4(),
        task_id=task_id,
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
            sample_id=sample_id,
            task_id=task_id,
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


def test_agent_command_rejects_user_supplied_context_flags() -> None:
    output = execute_workflow_command(
        f"inspect resource-list --scope visible --sample-id {uuid4()}",
        context=_context(),
        session_factory=_Session,
        service=_Service(resource=None),  # type: ignore[arg-type]
    )

    assert output.exit_code == 2
    assert output.stderr is not None
    assert "scope/context flags are injected" in output.stderr


def test_parse_error_returns_nonzero_output_instead_of_system_exit() -> None:
    output = execute_workflow_command(
        "inspect resource-content",
        context=_context(),
        session_factory=_Session,
        service=_Service(resource=None),  # type: ignore[arg-type]
    )

    assert output.exit_code == 2
    assert output.stderr is not None
    assert "--resource-id" in output.stderr


def test_invalid_resource_scope_returns_choices_without_service_call() -> None:
    output = execute_workflow_command(
        "inspect resource-list --scope all",
        context=_context(),
        session_factory=_Session,
        service=_Service(resource=None),  # type: ignore[arg-type]
    )

    assert output.exit_code == 2
    assert output.stderr is not None
    assert "invalid choice: 'all'" in output.stderr
    assert "visible" in output.stderr
    assert "descendants" in output.stderr
    assert "workflow inspect resource-list --help" in output.stderr


def test_invalid_resource_kind_returns_choices_without_service_call() -> None:
    output = execute_workflow_command(
        "inspect resource-list --scope visible --kind everything",
        context=_context(),
        session_factory=_Session,
        service=_Service(resource=None),  # type: ignore[arg-type]
    )

    assert output.exit_code == 2
    assert output.stderr is not None
    assert "invalid choice: 'everything'" in output.stderr
    assert "report" in output.stderr
    assert "search_cache" in output.stderr
    assert "workflow inspect resource-list --help" in output.stderr


def test_malformed_resource_uuid_returns_nonzero_output() -> None:
    output = execute_workflow_command(
        "inspect resource-content --resource-id not-a-uuid",
        context=_context(),
        session_factory=_Session,
        service=_Service(resource=None),  # type: ignore[arg-type]
    )

    assert output.exit_code == 2
    assert output.stderr is not None
    assert "badly formed hexadecimal UUID string" in output.stderr


def test_service_validation_error_returns_nonzero_output() -> None:
    output = execute_workflow_command(
        "inspect resource-list --scope visible",
        context=_context(),
        session_factory=_Session,
        service=_FailingService(),  # type: ignore[arg-type]
    )

    assert output.exit_code == 2
    assert output.stderr == "unsupported resource scope: all"


def test_manage_command_is_not_registered() -> None:
    output = execute_workflow_command(
        "manage add-subtask --task-slug child --description child",
        context=_context(),
        session_factory=_Session,
        service=object(),
    )

    assert output.exit_code == 2
    assert output.stderr is not None
    assert "invalid choice: 'manage'" in output.stderr
    assert "workflow manage --help" not in output.stderr


def test_task_tree_parent_task_id_filters_tasks_by_parent() -> None:
    parent_task_id = uuid4()
    service = _TaskTreeService()

    output = execute_workflow_command(
        f"inspect task-tree --parent-task-id {parent_task_id} --format json",
        context=_context(),
        session_factory=_Session,
        service=service,
    )

    payload = json.loads(output.stdout)
    assert output.exit_code == 0
    assert service.requested_parent_task_id == parent_task_id
    assert payload["tasks"][0]["parent_task_id"] == str(parent_task_id)


def test_human_cli_rejects_workflow_manage_surface() -> None:
    output = execute_workflow_command(
        "manage add-edge",
        context=_context(),
        session_factory=_Session,
        service=object(),
    )

    assert output.exit_code == 2
    assert output.stderr is not None
    assert "invalid choice: 'manage'" in output.stderr


def test_resource_list_rejects_removed_explain_flag() -> None:
    output = execute_workflow_command(
        "inspect resource-list --scope visible --explain",
        context=_context(),
        session_factory=_Session,
        service=_Service(resource=None),  # type: ignore[arg-type]
    )

    assert output.exit_code == 2
    assert output.stderr is not None
    assert "unrecognized arguments: --explain" in output.stderr
