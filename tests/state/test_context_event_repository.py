"""State tests for ContextEventRepository.

Exercises the append-only write path and sequence counter behaviour.
Uses the module-scoped SQLite engine from conftest.py.
"""

import asyncio
from uuid import UUID, uuid4

import pytest
from sqlmodel import Session

from ergon_core.api.generation import (
    GenerationTurn,
    SystemPromptPart,
    TextPart,
    ThinkingPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from ergon_core.core.persistence.context.event_payloads import (
    AssistantTextPayload,
    SystemPromptPayload,
    ThinkingPayload,
    ToolCallPayload,
    ToolResultPayload,
    UserMessagePayload,
)
from ergon_core.core.persistence.context.repository import ContextEventRepository
from ergon_core.core.persistence.shared.enums import RunStatus, TaskExecutionStatus
from ergon_core.core.persistence.telemetry.models import RunRecord, RunTaskExecution
from tests.state.factories import seed_flat_tasks, seed_run


def _seed_execution(session: Session, run_id: UUID, definition_id: UUID) -> UUID:
    """Create a RunTaskExecution row for testing."""
    exec_id = uuid4()
    # Get a task id from the definition
    from ergon_core.core.persistence.definitions.models import ExperimentDefinitionTask

    from sqlmodel import select

    task = session.exec(
        select(ExperimentDefinitionTask).where(
            ExperimentDefinitionTask.experiment_definition_id == definition_id
        )
    ).first()
    assert task is not None, "No task found for definition"

    session.add(
        RunTaskExecution(
            id=exec_id,
            run_id=run_id,
            definition_task_id=task.id,
            status=TaskExecutionStatus.RUNNING,
        )
    )
    session.flush()
    return exec_id


def _run_async(coro):
    return asyncio.run(coro)


class TestPersistTurnSimpleText:
    def test_text_only_turn_creates_events(self, session: Session):
        def_id, _inst_id, _task_ids = seed_flat_tasks(session, 1)
        run_id = seed_run(session, def_id)
        exec_id = _seed_execution(session, run_id, def_id)

        repo = ContextEventRepository()
        turn = GenerationTurn(
            messages_in=[
                SystemPromptPart(content="You are helpful."),
                UserPromptPart(content="Hello"),
            ],
            response_parts=[
                TextPart(content="Hi there!"),
            ],
        )

        events = _run_async(
            repo.persist_turn(
                session,
                run_id=run_id,
                execution_id=exec_id,
                worker_binding_key="test-worker",
                turn=turn,
            )
        )

        assert len(events) == 3
        assert events[0].event_type == "system_prompt"
        assert events[1].event_type == "user_message"
        assert events[2].event_type == "assistant_text"

    def test_events_have_ascending_sequence(self, session: Session):
        def_id, _inst_id, _task_ids = seed_flat_tasks(session, 1)
        run_id = seed_run(session, def_id)
        exec_id = _seed_execution(session, run_id, def_id)

        repo = ContextEventRepository()
        turn = GenerationTurn(
            messages_in=[
                SystemPromptPart(content="sys"),
                UserPromptPart(content="hi"),
            ],
            response_parts=[TextPart(content="hello")],
        )

        events = _run_async(
            repo.persist_turn(
                session,
                run_id=run_id,
                execution_id=exec_id,
                worker_binding_key="w",
                turn=turn,
            )
        )

        seqs = [e.sequence for e in events]
        assert seqs == list(range(len(seqs)))

    def test_payload_round_trips(self, session: Session):
        def_id, _inst_id, _task_ids = seed_flat_tasks(session, 1)
        run_id = seed_run(session, def_id)
        exec_id = _seed_execution(session, run_id, def_id)

        repo = ContextEventRepository()
        turn = GenerationTurn(
            messages_in=[UserPromptPart(content="What is 2+2?")],
            response_parts=[TextPart(content="4")],
        )

        events = _run_async(
            repo.persist_turn(
                session,
                run_id=run_id,
                execution_id=exec_id,
                worker_binding_key="w",
                turn=turn,
            )
        )

        user_event = events[0]
        parsed = user_event.parsed_payload()
        assert isinstance(parsed, UserMessagePayload)
        assert parsed.text == "What is 2+2?"

        text_event = events[1]
        parsed_text = text_event.parsed_payload()
        assert isinstance(parsed_text, AssistantTextPayload)
        assert parsed_text.text == "4"


class TestPersistTurnWithToolCall:
    def test_tool_call_events_created(self, session: Session):
        def_id, _inst_id, _task_ids = seed_flat_tasks(session, 1)
        run_id = seed_run(session, def_id)
        exec_id = _seed_execution(session, run_id, def_id)

        repo = ContextEventRepository()
        turn = GenerationTurn(
            messages_in=[
                SystemPromptPart(content="sys"),
                UserPromptPart(content="call the tool"),
            ],
            response_parts=[
                ToolCallPart(
                    tool_name="my_tool",
                    tool_call_id="call-1",
                    args={"param": "value"},
                ),
            ],
        )

        events = _run_async(
            repo.persist_turn(
                session,
                run_id=run_id,
                execution_id=exec_id,
                worker_binding_key="w",
                turn=turn,
            )
        )

        assert len(events) == 3
        assert events[2].event_type == "tool_call"
        parsed = events[2].parsed_payload()
        assert isinstance(parsed, ToolCallPayload)
        assert parsed.tool_name == "my_tool"
        assert parsed.tool_call_id == "call-1"
        assert parsed.args == {"param": "value"}

    def test_tool_result_from_messages_in(self, session: Session):
        def_id, _inst_id, _task_ids = seed_flat_tasks(session, 1)
        run_id = seed_run(session, def_id)
        exec_id = _seed_execution(session, run_id, def_id)

        repo = ContextEventRepository()
        # Simulate second turn: messages_in includes tool return from previous turn
        turn = GenerationTurn(
            messages_in=[
                ToolReturnPart(
                    tool_call_id="call-1",
                    tool_name="my_tool",
                    content="result text",
                ),
                UserPromptPart(content="continue"),
            ],
            response_parts=[TextPart(content="done")],
        )

        events = _run_async(
            repo.persist_turn(
                session,
                run_id=run_id,
                execution_id=exec_id,
                worker_binding_key="w",
                turn=turn,
            )
        )

        # user_message, assistant_text, tool_result
        event_types = [e.event_type for e in events]
        assert "tool_result" in event_types
        tool_result_event = next(e for e in events if e.event_type == "tool_result")
        parsed = tool_result_event.parsed_payload()
        assert isinstance(parsed, ToolResultPayload)
        assert parsed.tool_call_id == "call-1"
        assert parsed.tool_name == "my_tool"


class TestPersistTurnWithThinking:
    def test_thinking_event_created(self, session: Session):
        def_id, _inst_id, _task_ids = seed_flat_tasks(session, 1)
        run_id = seed_run(session, def_id)
        exec_id = _seed_execution(session, run_id, def_id)

        repo = ContextEventRepository()
        turn = GenerationTurn(
            messages_in=[UserPromptPart(content="think hard")],
            response_parts=[
                ThinkingPart(content="hmm..."),
                TextPart(content="answer"),
            ],
        )

        events = _run_async(
            repo.persist_turn(
                session,
                run_id=run_id,
                execution_id=exec_id,
                worker_binding_key="w",
                turn=turn,
            )
        )

        event_types = [e.event_type for e in events]
        assert "thinking" in event_types
        assert "assistant_text" in event_types

        thinking_event = next(e for e in events if e.event_type == "thinking")
        parsed = thinking_event.parsed_payload()
        assert isinstance(parsed, ThinkingPayload)
        assert parsed.text == "hmm..."


class TestSequenceCounterAccumulation:
    def test_sequence_continues_across_turns(self, session: Session):
        def_id, _inst_id, _task_ids = seed_flat_tasks(session, 1)
        run_id = seed_run(session, def_id)
        exec_id = _seed_execution(session, run_id, def_id)

        repo = ContextEventRepository()

        turn1 = GenerationTurn(
            messages_in=[UserPromptPart(content="first")],
            response_parts=[TextPart(content="reply 1")],
        )
        events1 = _run_async(
            repo.persist_turn(
                session,
                run_id=run_id,
                execution_id=exec_id,
                worker_binding_key="w",
                turn=turn1,
            )
        )

        turn2 = GenerationTurn(
            messages_in=[UserPromptPart(content="second")],
            response_parts=[TextPart(content="reply 2")],
        )
        events2 = _run_async(
            repo.persist_turn(
                session,
                run_id=run_id,
                execution_id=exec_id,
                worker_binding_key="w",
                turn=turn2,
            )
        )

        # Sequences must be strictly increasing across turns
        all_seqs = [e.sequence for e in events1] + [e.sequence for e in events2]
        assert all_seqs == list(range(len(all_seqs)))


class TestGetForExecution:
    def test_get_for_execution_returns_ordered_events(self, session: Session):
        def_id, _inst_id, _task_ids = seed_flat_tasks(session, 1)
        run_id = seed_run(session, def_id)
        exec_id = _seed_execution(session, run_id, def_id)

        repo = ContextEventRepository()
        turn = GenerationTurn(
            messages_in=[
                SystemPromptPart(content="sys"),
                UserPromptPart(content="hi"),
            ],
            response_parts=[TextPart(content="hello")],
        )
        _run_async(
            repo.persist_turn(
                session,
                run_id=run_id,
                execution_id=exec_id,
                worker_binding_key="w",
                turn=turn,
            )
        )

        fetched = repo.get_for_execution(session, exec_id)
        assert len(fetched) == 3
        seqs = [e.sequence for e in fetched]
        assert seqs == sorted(seqs)

    def test_get_for_execution_filters_by_execution(self, session: Session):
        def_id, _inst_id, _task_ids = seed_flat_tasks(session, 1)
        run_id = seed_run(session, def_id)
        exec_id_a = _seed_execution(session, run_id, def_id)
        exec_id_b = _seed_execution(session, run_id, def_id)

        repo = ContextEventRepository()
        for exec_id in (exec_id_a, exec_id_b):
            turn = GenerationTurn(
                messages_in=[UserPromptPart(content="hi")],
                response_parts=[TextPart(content="hello")],
            )
            _run_async(
                repo.persist_turn(
                    session,
                    run_id=run_id,
                    execution_id=exec_id,
                    worker_binding_key="w",
                    turn=turn,
                )
            )

        events_a = repo.get_for_execution(session, exec_id_a)
        events_b = repo.get_for_execution(session, exec_id_b)
        assert all(e.task_execution_id == exec_id_a for e in events_a)
        assert all(e.task_execution_id == exec_id_b for e in events_b)


class TestTokenIdsAndLogprobsOnFirstEvent:
    def test_token_ids_on_first_model_output_only(self, session: Session):
        def_id, _inst_id, _task_ids = seed_flat_tasks(session, 1)
        run_id = seed_run(session, def_id)
        exec_id = _seed_execution(session, run_id, def_id)

        from ergon_core.api.generation import TokenLogprob

        repo = ContextEventRepository()
        turn = GenerationTurn(
            messages_in=[UserPromptPart(content="q")],
            response_parts=[
                ThinkingPart(content="think"),
                TextPart(content="answer"),
            ],
            turn_token_ids=[1, 2, 3],
            turn_logprobs=[TokenLogprob(token="a", logprob=-0.1)],
        )

        events = _run_async(
            repo.persist_turn(
                session,
                run_id=run_id,
                execution_id=exec_id,
                worker_binding_key="w",
                turn=turn,
            )
        )

        thinking_event = next(e for e in events if e.event_type == "thinking")
        text_event = next(e for e in events if e.event_type == "assistant_text")

        thinking_parsed = thinking_event.parsed_payload()
        assert isinstance(thinking_parsed, ThinkingPayload)
        assert thinking_parsed.turn_token_ids == [1, 2, 3]
        assert thinking_parsed.turn_logprobs is not None
        assert len(thinking_parsed.turn_logprobs) == 1

        text_parsed = text_event.parsed_payload()
        assert isinstance(text_parsed, AssistantTextPayload)
        # Second model output event should NOT hold token_ids/logprobs
        assert text_parsed.turn_token_ids is None
        assert text_parsed.turn_logprobs is None
