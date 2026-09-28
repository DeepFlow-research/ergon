"""Protect source message previews and native task scoping at the model boundary."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from ergon_builtins.benchmarks.manager_gym.communication import MAGCommunication


@pytest.mark.asyncio
async def test_source_previews_ordering_and_task_filter(monkeypatch):
    task = str(uuid4())
    other_task = str(uuid4())
    now = datetime.now(UTC)

    def message(sender, recipient, content, age, logical):
        return SimpleNamespace(
            from_agent_id=sender,
            to_agent_id=recipient,
            content=content,
            created_at=now - timedelta(minutes=age),
            metadata_json={"logical_task_id": logical},
        )

    rows = [
        message("manager_agent", "alice", "a" * 300, 3, task),
        message("alice", "bob", "b" * 300, 2, other_task),
        message("manager_agent", "alice", "new", 1, task),
    ]
    communication = MAGCommunication(
        context=None,
        actor="alice",
        recipients=["manager_agent", "bob"],
        logical_task=task,
        timestep=0,
    )
    monkeypatch.setattr(communication, "read_messages", lambda: rows)
    recent = await communication.get_recent_messages(hours=1, limit=10)
    assert recent.splitlines()[0].endswith("manager_agent: new")
    assert recent.splitlines()[1].endswith("a" * 97 + "...")
    assert "b" * 100 not in recent
    conversation = await communication.get_conversation_with("manager_agent")
    assert conversation.splitlines()[1].endswith("a" * 147 + "...")
    assert conversation.splitlines()[2].endswith("new")
    task_messages = await communication.get_task_messages()
    assert "(2 found)" in task_messages and "a" * 97 + "..." in task_messages
    assert "b" * 100 not in task_messages
    assert (await communication.get_task_messages("invalid")).startswith("Invalid task ID")
    assert await communication.get_recent_messages(hours=0) == "📭 No recent messages"


@pytest.mark.asyncio
async def test_rejected_recipient_reports_available_native_bindings():
    communication = MAGCommunication(
        context=None,
        actor="alice",
        recipients=["manager_agent", "bob"],
        logical_task=str(uuid4()),
        timestep=0,
    )
    result = await communication.send_message("unknown", "message")
    assert result == "Unknown or unavailable recipient. Available agent IDs: manager_agent, bob"
