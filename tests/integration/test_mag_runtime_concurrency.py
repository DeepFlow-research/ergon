"""Real PostgreSQL serialization contracts required by concurrent native agents."""

from pathlib import Path
import runpy
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text, inspect

import asyncio
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import event
from sqlmodel import select

from ergon_core.core.application.communication import service as communication_module
from ergon_core.core.application.communication.models import CreateMessageRequest
from ergon_core.core.application.runtime.graph_repository import RuntimeGraphRepository
from ergon_core.core.persistence.shared.db import get_engine, get_session
from ergon_core.core.persistence.telemetry.models import SampleRecord, ThreadMessage


@pytest.fixture
def sample(monkeypatch):
    assert get_engine().dialect.name == "postgresql", "This contract requires real PostgreSQL"
    row = SampleRecord(
        benchmark_type="mag-postgres-contract",
        instance_key=str(uuid4()),
        worker_team_json={},
        status="completed",
    )
    with get_session() as session:
        session.add(row)
        session.commit()
        session.refresh(row)
        sample_id = row.id
    monkeypatch.setattr(
        communication_module,
        "get_dashboard_event_publisher",
        lambda: SimpleNamespace(publish=AsyncMock()),
    )
    return sample_id


def test_message_sequence_and_dedup_are_atomic(sample):
    service = communication_module.CommunicationService()
    request = CreateMessageRequest(
        sample_id=sample,
        from_agent_id="alice",
        to_agent_id="bob",
        thread_topic="concurrency",
        content="seed",
    )
    seed = asyncio.run(service.save_message(request))
    barrier = Barrier(2, timeout=15)

    def before_lock(conn, cursor, statement, parameters, context, executemany):
        if "FOR UPDATE" in statement and "threads" in statement:
            barrier.wait()

    def send(index):
        return asyncio.run(
            service.save_message(
                request.model_copy(
                    update={
                        "content": f"message-{index}",
                        "idempotency_key": f"message-{index}",
                        "metadata": {"index": index},
                    }
                )
            )
        )

    engine = get_engine()
    event.listen(engine, "before_cursor_execute", before_lock)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            distinct = list(pool.map(send, [1, 2]))
            replay = list(pool.map(send, [3, 3]))
    finally:
        event.remove(engine, "before_cursor_execute", before_lock)
    assert sorted(m.sequence_num for m in distinct) == [2, 3]
    assert replay[0].message_id == replay[1].message_id
    with get_session() as session:
        rows = session.exec(
            select(ThreadMessage).where(ThreadMessage.thread_id == seed.thread_id)
        ).all()
        assert len(rows) == 4 and {row.sequence_num for row in rows} == {1, 2, 3, 4}
    with pytest.raises(ValueError, match="idempotency"):
        asyncio.run(
            service.save_message(
                request.model_copy(update={"content": "changed", "idempotency_key": "message-3"})
            )
        )


@pytest.mark.asyncio
async def test_graph_lock_does_not_block_the_event_loop(sample):
    repo = RuntimeGraphRepository()
    first, second = get_session(), get_session()
    try:
        await repo.lock_sample(first, sample)
        waiting = asyncio.create_task(repo.lock_sample(second, sample))
        # If acquisition blocks the event loop, this coroutine cannot release
        # the lock and the test's outer timeout catches the deadlock.
        await asyncio.sleep(0.1)
        assert not waiting.done()
        first.commit()
        await asyncio.wait_for(waiting, timeout=5)
    finally:
        first.close()
        second.close()


def test_historical_duplicate_messages_migrate_without_loss():

    schema = "mag_migration_" + uuid4().hex
    root = Path(__file__).resolve().parents[2]
    with get_engine().connect() as connection:
        connection.execute(text(f"CREATE SCHEMA {schema}"))
        connection.execute(text(f"SET search_path TO {schema}"))
        connection.execute(
            text(
                "CREATE TABLE thread_messages (id TEXT PRIMARY KEY, thread_id TEXT NOT NULL, sequence_num INTEGER NOT NULL, created_at TIMESTAMP NOT NULL)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO thread_messages VALUES ('first','thread',1,'2026-01-01'),('second','thread',1,'2026-01-02'),('third','thread',2,'2026-01-03')"
            )
        )
        try:
            with Operations.context(MigrationContext.configure(connection)):
                for filename in ["00000004_message_idempotency.py", "00000005_message_metadata.py"]:
                    upgrade = runpy.run_path(root / "ergon_core/migrations/versions" / filename)[
                        "upgrade"
                    ]
                    upgrade()
                    upgrade()  # Fresh/current metadata and repeat application both remain safe.
            rows = connection.execute(
                text(
                    "SELECT id, sequence_num, metadata_json FROM thread_messages ORDER BY sequence_num"
                )
            ).all()
            assert [(r.id, r.sequence_num) for r in rows] == [
                ("first", 1),
                ("second", 2),
                ("third", 3),
            ]
            assert all(r.metadata_json == {} for r in rows)
            assert {
                c["name"] for c in inspect(connection).get_unique_constraints("thread_messages")
            } >= {"uq_thread_message_sequence", "uq_thread_message_action"}
        finally:
            connection.execute(text("SET search_path TO public"))
            connection.execute(text(f"DROP SCHEMA {schema} CASCADE"))
            connection.commit()
