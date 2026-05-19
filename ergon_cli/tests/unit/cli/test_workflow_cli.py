import json
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from ergon_cli.commands.workflow import WorkflowCommandContext, execute_workflow_command
from ergon_core.core.application.graph.models import GraphTaskRef
from ergon_core.core.application.workflows.models import WorkflowMutationRef
from ergon_core.core.application.workflows.models import WorkflowResourceRef


class _Session:
    def close(self) -> None:
        pass


@dataclass
class _Service:
    resource: WorkflowResourceRef

    def list_resources(self, session, *, run_id, node_id, scope, kind=None, max_depth=3, limit=50):
        assert isinstance(session, _Session)
        assert run_id == self.resource.run_id
        assert node_id == self.resource.node_id
        assert scope == "visible"
        assert kind is None
        assert max_depth == 3
        assert limit == 5
        return [self.resource]


class _ManagingService:
    def __init__(self) -> None:
        self.added = None

    async def add_task(
        self,
        session,
        *,
        run_id,
        parent_task_id,
        task_slug,
        description,
        assigned_worker_slug,
        dry_run,
    ):
        assert isinstance(session, _Session)
        self.added = {
            "run_id": run_id,
            "parent_task_id": parent_task_id,
            "task_slug": task_slug,
            "description": description,
            "assigned_worker_slug": assigned_worker_slug,
            "dry_run": dry_run,
        }

        return WorkflowMutationRef(
            action="add-task",
            dry_run=dry_run,
            node=GraphTaskRef(
                task_id=uuid4(),
                task_slug="source-scout",
                status="pending",
                level=1,
                parent_task_id=parent_task_id,
                assigned_worker_slug=assigned_worker_slug,
                description=description,
            ),
            message="Added task source-scout",
        )


class _FailingService:
    def list_resources(self, *args, **kwargs):
        raise ValueError("unsupported resource scope: all")


def _context() -> WorkflowCommandContext:
    return WorkflowCommandContext(
        run_id=uuid4(),
        node_id=uuid4(),
        execution_id=uuid4(),
        sandbox_task_key=uuid4(),
        benchmark_type="researchrubrics",
    )


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
        service=_Service(resource),
    )

    payload = json.loads(output.stdout)

    assert output.exit_code == 0
    assert payload["resources"][0]["name"] == "paper.txt"
    assert payload["resources"][0]["task_slug"] == "research"


def test_agent_command_rejects_user_supplied_context_flags() -> None:
    output = execute_workflow_command(
        f"inspect resource-list --scope visible --run-id {uuid4()}",
        context=_context(),
        session_factory=_Session,
        service=_Service(resource=None),  # type: ignore[arg-type]
    )

    assert output.exit_code == 2
    assert output.stderr is not None
    assert "scope/context flags are injected" in output.stderr


def test_parse_error_returns_nonzero_output_instead_of_system_exit() -> None:
    output = execute_workflow_command(
        "manage materialize-resource",
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


def test_manage_add_task_creates_subtask_with_injected_parent_context() -> None:
    run_id = uuid4()
    node_id = uuid4()
    service = _ManagingService()

    output = execute_workflow_command(
        "manage add-task --task-slug source-scout "
        "--worker researchrubrics-researcher "
        "--description 'Find authoritative sources' "
        "--format json",
        context=WorkflowCommandContext(
            run_id=run_id,
            node_id=node_id,
            execution_id=uuid4(),
            sandbox_task_key=uuid4(),
            benchmark_type="researchrubrics",
        ),
        session_factory=_Session,
        service=service,
    )

    payload = json.loads(output.stdout)
    assert output.exit_code == 0
    assert payload["task"]["node"]["task_slug"] == "source-scout"
    assert service.added == {
        "run_id": run_id,
        "parent_task_id": node_id,
        "task_slug": "source-scout",
        "description": "Find authoritative sources",
        "assigned_worker_slug": "researchrubrics-researcher",
        "dry_run": False,
    }
