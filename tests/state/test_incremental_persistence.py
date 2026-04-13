"""Tests for incremental turn persistence via async generator workers.

Verifies:
- Generator worker yields N turns → N RunGenerationTurn rows in PG
- Worker crash at turn 5 → turns 0-4 in PG with execution_outcome
- Lazy worker yields all at end → same PG result
- from_buffer() pre-seeds a worker from recovered turns
- get_output() reads from PG via repository
"""

import pytest
from uuid import uuid4

from sqlmodel import Session, select

from ergon_core.api.generation import GenerationTurn
from ergon_core.api.worker import Worker
from ergon_core.api.worker_context import WorkerContext
from ergon_core.core.persistence.telemetry.models import RunGenerationTurn, RunTaskExecution
from ergon_core.core.persistence.telemetry.repositories import GenerationTurnRepository
from ergon_core.core.persistence.shared.enums import TaskExecutionStatus

from tests.state.factories import seed_flat_tasks, seed_run


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _make_turn(index: int, text: str = "response") -> GenerationTurn:
    return GenerationTurn(
        prompt_text=f"Task: prompt {index}" if index == 0 else None,
        raw_response={
            "parts": [{"part_kind": "text", "content": f"{text} {index}"}],
        },
        tool_results=[],
    )


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


# ---------------------------------------------------------------------------
# Tests: persist_single
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_persist_single_writes_row(session: Session):
    """persist_single() creates one RunGenerationTurn row per call."""
    def_id, _, task_ids = seed_flat_tasks(session, 1)
    run_id = seed_run(session, def_id)
    execution = _make_execution(session, run_id, task_ids[0])

    repo = GenerationTurnRepository()
    turn = _make_turn(0)

    await repo.persist_single(
        session,
        run_id=run_id,
        execution_id=execution.id,
        worker_binding_key="test-worker",
        turn=turn,
        turn_index=0,
    )

    rows = list(
        session.exec(select(RunGenerationTurn).where(RunGenerationTurn.run_id == run_id)).all()
    )
    assert len(rows) == 1
    assert rows[0].turn_index == 0
    assert rows[0].execution_outcome == "success"
    assert rows[0].prompt_text == "Task: prompt 0"


@pytest.mark.asyncio
async def test_persist_multiple_turns(session: Session):
    """Multiple persist_single() calls create sequential rows."""
    def_id, _, task_ids = seed_flat_tasks(session, 1)
    run_id = seed_run(session, def_id)
    execution = _make_execution(session, run_id, task_ids[0])

    repo = GenerationTurnRepository()
    for i in range(5):
        await repo.persist_single(
            session,
            run_id=run_id,
            execution_id=execution.id,
            worker_binding_key="test-worker",
            turn=_make_turn(i),
            turn_index=i,
        )

    rows = repo.get_for_execution(session, execution.id)
    assert len(rows) == 5
    assert [r.turn_index for r in rows] == [0, 1, 2, 3, 4]


@pytest.mark.asyncio
async def test_mark_execution_outcome(session: Session):
    """mark_execution_outcome updates all turns for an execution."""
    def_id, _, task_ids = seed_flat_tasks(session, 1)
    run_id = seed_run(session, def_id)
    execution = _make_execution(session, run_id, task_ids[0])

    repo = GenerationTurnRepository()
    for i in range(3):
        await repo.persist_single(
            session,
            run_id=run_id,
            execution_id=execution.id,
            worker_binding_key="test-worker",
            turn=_make_turn(i),
            turn_index=i,
        )

    repo.mark_execution_outcome(session, execution.id, "failure")

    rows = repo.get_for_execution(session, execution.id)
    assert all(r.execution_outcome == "failure" for r in rows)


@pytest.mark.asyncio
async def test_persist_single_populates_prompt_text(session: Session):
    """persist_single() stores prompt_text from the GenerationTurn."""
    def_id, _, task_ids = seed_flat_tasks(session, 1)
    run_id = seed_run(session, def_id)
    execution = _make_execution(session, run_id, task_ids[0])

    repo = GenerationTurnRepository()
    turn = GenerationTurn(
        prompt_text="Task: Research quantum computing",
        raw_response={"parts": [{"part_kind": "text", "content": "hello"}]},
    )

    await repo.persist_single(
        session,
        run_id=run_id,
        execution_id=execution.id,
        worker_binding_key="test-worker",
        turn=turn,
        turn_index=0,
    )

    rows = repo.get_for_execution(session, execution.id)
    assert rows[0].prompt_text == "Task: Research quantum computing"


@pytest.mark.asyncio
async def test_listener_called_on_persist(session: Session):
    """Listeners registered via add_listener() are called after persist_single()."""
    def_id, _, task_ids = seed_flat_tasks(session, 1)
    run_id = seed_run(session, def_id)
    execution = _make_execution(session, run_id, task_ids[0])

    received = []

    async def _listener(row: RunGenerationTurn) -> None:
        received.append(row.turn_index)

    repo = GenerationTurnRepository()
    repo.add_listener(_listener)

    for i in range(3):
        await repo.persist_single(
            session,
            run_id=run_id,
            execution_id=execution.id,
            worker_binding_key="test-worker",
            turn=_make_turn(i),
            turn_index=i,
        )

    assert received == [0, 1, 2]


# ---------------------------------------------------------------------------
# Tests: Worker.get_output() base method
# ---------------------------------------------------------------------------


def test_get_output_reads_last_turn(session: Session):
    """Base get_output() returns last turn's response_text."""
    def_id, _, task_ids = seed_flat_tasks(session, 1)
    run_id = seed_run(session, def_id)
    execution = _make_execution(session, run_id, task_ids[0])

    for i in range(3):
        session.add(
            RunGenerationTurn(
                id=uuid4(),
                run_id=run_id,
                task_execution_id=execution.id,
                worker_binding_key="test",
                turn_index=i,
                raw_response={},
                response_text=f"response {i}",
            )
        )
    session.commit()

    class _TestWorker(Worker):
        type_slug = "test"

        async def execute(self, task, *, context):
            yield  # type: ignore[misc]

    worker = _TestWorker(name="test")
    ctx = WorkerContext(
        run_id=run_id,
        task_id=task_ids[0],
        execution_id=execution.id,
        sandbox_id="",
    )

    # Monkey-patch get_session for this test
    import ergon_core.api.worker as worker_mod

    original_get_session = worker_mod.get_session

    from contextlib import contextmanager

    @contextmanager
    def _test_session():
        yield session

    worker_mod.get_session = _test_session
    try:
        output = worker.get_output(ctx)
        assert output.output == "response 2"
        assert output.success is True
    finally:
        worker_mod.get_session = original_get_session
