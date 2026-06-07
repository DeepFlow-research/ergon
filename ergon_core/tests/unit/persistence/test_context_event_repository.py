from uuid import uuid4

import pytest
from ergon_core.core.shared.context_parts import (
    AssistantTextPart,
    ContextPartChunk,
    ContextPartChunkLog,
    ProviderTokenUsage,
    ThinkingPart,
    ToolCallPart,
    ToolResultPart,
    UserMessagePart,
)
from ergon_core.core.persistence.context.models import SampleContextEvent
from ergon_core.core.application.context.service import ContextEventService
from ergon_core.core.persistence.definitions.models import ExperimentDefinition
from ergon_core.core.persistence.graph.models import SampleGraphNode
from ergon_core.core.persistence.shared.enums import SampleStatus, TaskExecutionStatus
from ergon_core.core.persistence.telemetry.models import (
    SampleRecord,
    SampleTaskAttempt,
)
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
    sample_id = uuid4()
    definition_id = uuid4()
    task_id = uuid4()
    node = SampleGraphNode(
        sample_id=sample_id,
        task_id=task_id,
        instance_key="instance",
        task_slug="task",
        description="Task",
        status="running",
        assigned_worker_slug="worker",
    )
    session.add(
        ExperimentDefinition(
            id=definition_id,
            benchmark_type="unit",
            name="unit",
            metadata_json={},
        )
    )
    session.add(
        SampleRecord(
            id=sample_id,
            definition_id=definition_id,
            benchmark_type="unit",
            instance_key="instance",
            status=SampleStatus.EXECUTING,
        )
    )
    session.add(node)
    session.flush()
    execution = SampleTaskAttempt(
        sample_id=sample_id,
        task_id=node.task_id,
        node_id=node.task_id,
        status=TaskExecutionStatus.RUNNING,
    )
    session.add(execution)
    session.commit()
    return sample_id, execution.id


def test_run_context_event_parsed_payload_is_context_part_chunk_log() -> None:
    log = ContextPartChunkLog(
        part=AssistantTextPart(content="hello"),
        sequence=3,
        worker_binding_key="worker-a",
        turn_id="turn-1",
    )
    event = SampleContextEvent(
        sample_id=uuid4(),
        task_execution_id=uuid4(),
        worker_binding_key="worker-a",
        sequence=3,
        event_type="assistant_text",
        payload=log.model_dump(mode="json"),
    )

    parsed = event.parsed_payload()

    assert isinstance(parsed, ContextPartChunkLog)
    assert parsed.part == AssistantTextPart(content="hello")


@pytest.mark.asyncio
async def test_persist_chunk_records_prompt_and_model_output_in_order() -> None:
    session = _session()
    sample_id, execution_id = _execution_fixture(session)
    repo = ContextEventService()

    await repo.persist_chunk(
        session,
        sample_id=sample_id,
        execution_id=execution_id,
        worker_binding_key="worker",
        chunk=ContextPartChunk(part=UserMessagePart(content="question")),
    )
    await repo.persist_chunk(
        session,
        sample_id=sample_id,
        execution_id=execution_id,
        worker_binding_key="worker",
        chunk=ContextPartChunk(part=ThinkingPart(content="think")),
    )
    await repo.persist_chunk(
        session,
        sample_id=sample_id,
        execution_id=execution_id,
        worker_binding_key="worker",
        chunk=ContextPartChunk(part=AssistantTextPart(content="answer")),
    )

    events = repo.get_for_execution(session, execution_id)

    assert [event.sequence for event in events] == [0, 1, 2]
    assert [event.event_type for event in events] == [
        "user_message",
        "thinking",
        "assistant_text",
    ]
    assert events[1].parsed_payload().turn_id == events[2].parsed_payload().turn_id


@pytest.mark.asyncio
async def test_persist_chunk_records_provider_usage() -> None:
    session = _session()
    sample_id, execution_id = _execution_fixture(session)
    repo = ContextEventService()

    await repo.persist_chunk(
        session,
        sample_id=sample_id,
        execution_id=execution_id,
        worker_binding_key="worker",
        chunk=ContextPartChunk(
            part=AssistantTextPart(content="answer"),
            provider_usage=ProviderTokenUsage(
                prompt_tokens=5,
                completion_tokens=7,
                cached_tokens=2,
                total_cost_usd=0.03,
            ),
        ),
    )

    event = repo.get_for_execution(session, execution_id)[0]

    assert event.payload["provider_usage"] == {
        "prompt_tokens": 5,
        "completion_tokens": 7,
        "reasoning_tokens": None,
        "tool_call_tokens": None,
        "tool_result_tokens": None,
        "cached_tokens": 2,
        "total_tokens": None,
        "total_cost_usd": 0.03,
    }
    assert event.parsed_payload().provider_usage == ProviderTokenUsage(
        prompt_tokens=5,
        completion_tokens=7,
        cached_tokens=2,
        total_cost_usd=0.03,
    )


@pytest.mark.asyncio
async def test_persist_chunk_tool_result_closes_current_turn() -> None:
    session = _session()
    sample_id, execution_id = _execution_fixture(session)
    repo = ContextEventService()

    await repo.persist_chunk(
        session,
        sample_id=sample_id,
        execution_id=execution_id,
        worker_binding_key="worker",
        chunk=ContextPartChunk(
            part=ToolCallPart(tool_call_id="call-1", tool_name="search", args={"q": "x"})
        ),
    )
    await repo.persist_chunk(
        session,
        sample_id=sample_id,
        execution_id=execution_id,
        worker_binding_key="worker",
        chunk=ContextPartChunk(
            part=ToolResultPart(tool_call_id="call-1", tool_name="search", content="ok")
        ),
    )

    events = repo.get_for_execution(session, execution_id)

    assert [event.event_type for event in events] == ["tool_call", "tool_result"]
    assert events[0].parsed_payload().turn_id is not None
    assert events[1].parsed_payload().turn_id is None
