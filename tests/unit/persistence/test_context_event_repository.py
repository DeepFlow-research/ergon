from uuid import uuid4

import pytest
from ergon_core.core.generation import (
    GenerationTurn,
    TextPart,
    ThinkingPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from ergon_core.core.persistence.context.repository import ContextEventRepository
from ergon_core.core.persistence.definitions.models import ExperimentDefinition
from ergon_core.core.persistence.graph.models import RunGraphNode
from ergon_core.core.persistence.shared.enums import RunStatus, TaskExecutionStatus
from ergon_core.core.persistence.telemetry.models import RunRecord, RunTaskExecution
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine


def _session() -> Session:
    _ = ExperimentDefinition
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _execution_fixture(session: Session) -> tuple:
    run_id = uuid4()
    node = RunGraphNode(
        run_id=run_id,
        instance_key="instance",
        task_slug="task",
        description="Task",
        status="running",
        assigned_worker_slug="worker",
    )
    session.add(RunRecord(id=run_id, experiment_definition_id=uuid4(), status=RunStatus.EXECUTING))
    session.add(node)
    session.flush()
    execution = RunTaskExecution(
        run_id=run_id,
        node_id=node.id,
        status=TaskExecutionStatus.RUNNING,
    )
    session.add(execution)
    session.commit()
    return run_id, execution.id


@pytest.mark.asyncio
async def test_persist_turn_records_tool_results_from_tool_results() -> None:
    session = _session()
    run_id, execution_id = _execution_fixture(session)

    events = await ContextEventRepository().persist_turn(
        session,
        run_id=run_id,
        execution_id=execution_id,
        worker_binding_key="worker",
        turn=GenerationTurn(
            messages_in=[UserPromptPart(content="search")],
            response_parts=[
                ToolCallPart(tool_name="search", tool_call_id="call-1", args={"query": "ergon"})
            ],
            tool_results=[
                ToolReturnPart(tool_name="search", tool_call_id="call-1", content="found")
            ],
        ),
    )

    assert [event.event_type for event in events] == ["user_message", "tool_call", "tool_result"]
    tool_result = events[-1].parsed_payload()
    assert tool_result.event_type == "tool_result"
    assert tool_result.tool_name == "search"
    assert tool_result.tool_call_id == "call-1"
    assert tool_result.result == "found"


@pytest.mark.asyncio
async def test_persist_turn_records_thinking_before_assistant_text() -> None:
    session = _session()
    run_id, execution_id = _execution_fixture(session)

    events = await ContextEventRepository().persist_turn(
        session,
        run_id=run_id,
        execution_id=execution_id,
        worker_binding_key="worker",
        turn=GenerationTurn(
            messages_in=[UserPromptPart(content="hard question")],
            response_parts=[
                ThinkingPart(content="let me think"),
                TextPart(content="answer"),
            ],
        ),
    )

    assert [event.event_type for event in events] == [
        "user_message",
        "thinking",
        "assistant_text",
    ]
