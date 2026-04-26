import json
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from ergon_cli.commands.workflow import WorkflowCommandContext, execute_workflow_command
from ergon_core.core.runtime.services.workflow_dto import WorkflowResourceRef


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
