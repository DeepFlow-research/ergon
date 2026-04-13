"""Tests for ThreadMessage.task_execution_id FK.

Verifies that messages can be linked to a specific task execution
and queried by that link, while remaining backward compatible with
None (messages not tied to a specific execution).
"""

from uuid import uuid4

from sqlmodel import Session, select

from ergon_core.core.persistence.shared.enums import TaskExecutionStatus
from ergon_core.core.persistence.telemetry.models import (
    ThreadMessage,
    Thread,
    RunTaskExecution,
)

from tests.state.factories import seed_flat_tasks, seed_run


def _make_thread(session: Session, run_id) -> Thread:
    thread = Thread(
        id=uuid4(),
        run_id=run_id,
        topic="test-topic",
        agent_a_id="agent-a",
        agent_b_id="agent-b",
    )
    session.add(thread)
    session.flush()
    return thread


def _make_execution(session: Session, run_id, task_id) -> RunTaskExecution:
    execution = RunTaskExecution(
        id=uuid4(),
        run_id=run_id,
        definition_task_id=task_id,
        status=TaskExecutionStatus.RUNNING,
    )
    session.add(execution)
    session.flush()
    return execution


def test_message_with_execution_id(session: Session):
    """A message with task_execution_id should persist it correctly."""
    def_id, _, task_ids = seed_flat_tasks(session, 1)
    run_id = seed_run(session, def_id)
    thread = _make_thread(session, run_id)
    execution = _make_execution(session, run_id, task_ids[0])

    msg = ThreadMessage(
        id=uuid4(),
        thread_id=thread.id,
        run_id=run_id,
        task_execution_id=execution.id,
        from_agent_id="agent-a",
        to_agent_id="agent-b",
        content="hello from execution",
        sequence_num=1,
    )
    session.add(msg)
    session.commit()

    loaded = session.get(ThreadMessage, msg.id)
    assert loaded is not None
    assert loaded.task_execution_id == execution.id


def test_message_without_execution_id(session: Session):
    """A message without task_execution_id should default to None."""
    def_id, _, _ = seed_flat_tasks(session, 1)
    run_id = seed_run(session, def_id)
    thread = _make_thread(session, run_id)

    msg = ThreadMessage(
        id=uuid4(),
        thread_id=thread.id,
        run_id=run_id,
        from_agent_id="agent-a",
        to_agent_id="agent-b",
        content="hello without execution",
        sequence_num=1,
    )
    session.add(msg)
    session.commit()

    loaded = session.get(ThreadMessage, msg.id)
    assert loaded is not None
    assert loaded.task_execution_id is None


def test_query_messages_by_execution_id(session: Session):
    """Messages can be filtered by task_execution_id."""
    def_id, _, task_ids = seed_flat_tasks(session, 2)
    run_id = seed_run(session, def_id)
    thread = _make_thread(session, run_id)
    exec_a = _make_execution(session, run_id, task_ids[0])
    exec_b = _make_execution(session, run_id, task_ids[1])

    for i, exec_id in enumerate([exec_a.id, exec_a.id, exec_b.id, None]):
        session.add(
            ThreadMessage(
                id=uuid4(),
                thread_id=thread.id,
                run_id=run_id,
                task_execution_id=exec_id,
                from_agent_id="agent-a",
                to_agent_id="agent-b",
                content=f"message {i}",
                sequence_num=i,
            )
        )
    session.commit()

    msgs_exec_a = list(
        session.exec(
            select(ThreadMessage).where(ThreadMessage.task_execution_id == exec_a.id)
        ).all()
    )
    assert len(msgs_exec_a) == 2

    msgs_exec_b = list(
        session.exec(
            select(ThreadMessage).where(ThreadMessage.task_execution_id == exec_b.id)
        ).all()
    )
    assert len(msgs_exec_b) == 1

    msgs_no_exec = list(
        session.exec(
            select(ThreadMessage).where(ThreadMessage.task_execution_id.is_(None))  # type: ignore[union-attr]
        ).all()
    )
    assert len(msgs_no_exec) == 1
