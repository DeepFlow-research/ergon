from collections.abc import Iterator
from uuid import uuid4

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from ergon_core.core.runtime.services import communication_service as module
from ergon_core.core.runtime.services.communication_schemas import CreateMessageRequest

Thread = module.Thread


@pytest.fixture()
def session_factory() -> Iterator[tuple[Session, object]]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    def _get_session() -> Session:
        return Session(engine)

    yield _get_session


@pytest.mark.asyncio
async def test_save_message_persists_thread_summary_and_emits_it(
    monkeypatch: pytest.MonkeyPatch,
    session_factory,
) -> None:
    emitted: list[tuple[object, object]] = []

    async def _record_thread_event(*, run_id, thread, message) -> None:  # noqa: ANN001
        emitted.append((thread, message))

    monkeypatch.setattr(module, "get_session", session_factory)
    monkeypatch.setattr(module.dashboard_emitter, "thread_message_created", _record_thread_event)

    run_id = uuid4()
    execution_id = uuid4()
    summary = "Leaf workers report completion artifacts and probe exit status."

    response = await module.CommunicationService().save_message(
        CreateMessageRequest(
            run_id=run_id,
            from_agent_id="leaf-l_1",
            to_agent_id="parent",
            thread_topic="smoke-completion",
            thread_summary=summary,
            content="l_1: done exit=0",
            task_execution_id=execution_id,
        )
    )

    with session_factory() as session:
        thread = session.exec(select(Thread).where(Thread.id == response.thread_id)).one()

    assert thread.summary == summary
    assert emitted
    thread_dto, message_dto = emitted[0]
    assert thread_dto.summary == summary
    assert message_dto.task_execution_id == str(execution_id)


@pytest.mark.asyncio
async def test_save_message_backfills_missing_summary_without_overwriting_existing(
    monkeypatch: pytest.MonkeyPatch,
    session_factory,
) -> None:
    async def _ignore_thread_event(*, run_id, thread, message) -> None:  # noqa: ANN001
        return None

    monkeypatch.setattr(module, "get_session", session_factory)
    monkeypatch.setattr(module.dashboard_emitter, "thread_message_created", _ignore_thread_event)

    service = module.CommunicationService()
    run_id = uuid4()
    await service.save_message(
        CreateMessageRequest(
            run_id=run_id,
            from_agent_id="leaf-l_1",
            to_agent_id="parent",
            thread_topic="smoke-completion",
            content="l_1: done exit=0",
        )
    )
    await service.save_message(
        CreateMessageRequest(
            run_id=run_id,
            from_agent_id="leaf-l_2",
            to_agent_id="parent",
            thread_topic="smoke-completion",
            thread_summary="Completion reports from leaf workers.",
            content="l_2: done exit=0",
        )
    )
    await service.save_message(
        CreateMessageRequest(
            run_id=run_id,
            from_agent_id="leaf-l_3",
            to_agent_id="parent",
            thread_topic="smoke-completion",
            thread_summary="Replacement summary should not win.",
            content="l_3: done exit=0",
        )
    )

    with session_factory() as session:
        thread = session.exec(select(Thread).where(Thread.run_id == run_id)).one()

    assert thread.summary == "Completion reports from leaf workers."
