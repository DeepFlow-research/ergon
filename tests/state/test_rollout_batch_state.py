"""Tests for durable rollout batch state in PG.

Verifies that RolloutBatch/RolloutBatchRun tables correctly replace
the in-memory _batches dict, and that batch state survives across
separate session scopes (simulating API restarts).
"""

from uuid import uuid4

from sqlmodel import Session, select

from ergon_core.core.persistence.shared.enums import RunStatus
from ergon_core.core.persistence.telemetry.models import (
    RolloutBatch,
    RolloutBatchRun,
    RunRecord,
)
from ergon_core.core.rl.rollout_types import BatchStatus

from tests.state.factories import seed_flat_tasks


def test_batch_and_runs_created(session: Session):
    """submit() should create a RolloutBatch row and RolloutBatchRun rows."""
    def_id, _, _ = seed_flat_tasks(session, 1)

    batch_id = uuid4()
    run_ids = [uuid4(), uuid4(), uuid4()]

    session.add(RolloutBatch(
        id=batch_id,
        definition_id=def_id,
        status=BatchStatus.PENDING,
    ))
    for rid in run_ids:
        session.add(RunRecord(
            id=rid,
            experiment_definition_id=def_id,
            status=RunStatus.PENDING,
        ))
        session.add(RolloutBatchRun(
            id=uuid4(),
            batch_id=batch_id,
            run_id=rid,
        ))
    session.commit()

    batch = session.get(RolloutBatch, batch_id)
    assert batch is not None
    assert batch.status == BatchStatus.PENDING

    batch_runs = list(session.exec(
        select(RolloutBatchRun).where(RolloutBatchRun.batch_id == batch_id)
    ).all())
    assert len(batch_runs) == 3
    assert {br.run_id for br in batch_runs} == set(run_ids)


def test_poll_reads_from_pg(session: Session):
    """Batch state should be queryable from PG (not in-memory)."""
    def_id, _, _ = seed_flat_tasks(session, 1)

    batch_id = uuid4()
    run_id = uuid4()

    session.add(RolloutBatch(id=batch_id, definition_id=def_id, status=BatchStatus.PENDING))
    session.add(RunRecord(id=run_id, experiment_definition_id=def_id, status=RunStatus.PENDING))
    session.add(RolloutBatchRun(id=uuid4(), batch_id=batch_id, run_id=run_id))
    session.commit()

    batch = session.get(RolloutBatch, batch_id)
    assert batch is not None

    batch_runs = list(session.exec(
        select(RolloutBatchRun).where(RolloutBatchRun.batch_id == batch_id)
    ).all())
    assert len(batch_runs) == 1
    assert batch_runs[0].run_id == run_id


def test_cancel_updates_batch_status(session: Session):
    """cancel() should set batch status to CANCELLED."""
    def_id, _, _ = seed_flat_tasks(session, 1)

    batch_id = uuid4()
    session.add(RolloutBatch(id=batch_id, definition_id=def_id, status=BatchStatus.RUNNING))
    session.commit()

    batch = session.get(RolloutBatch, batch_id)
    assert batch is not None
    batch.status = BatchStatus.CANCELLED
    session.add(batch)
    session.commit()

    refreshed = session.get(RolloutBatch, batch_id)
    assert refreshed is not None
    assert refreshed.status == BatchStatus.CANCELLED


def test_batch_survives_session_reset(session: Session):
    """Batch should be findable after committing and re-querying (simulates restart)."""
    def_id, _, _ = seed_flat_tasks(session, 1)

    batch_id = uuid4()
    run_id = uuid4()

    session.add(RolloutBatch(id=batch_id, definition_id=def_id, status=BatchStatus.PENDING))
    session.add(RunRecord(id=run_id, experiment_definition_id=def_id, status=RunStatus.COMPLETED))
    session.add(RolloutBatchRun(id=uuid4(), batch_id=batch_id, run_id=run_id))
    session.commit()

    found_batch = session.exec(
        select(RolloutBatch).where(RolloutBatch.id == batch_id)
    ).first()
    assert found_batch is not None
    assert found_batch.definition_id == def_id

    found_runs = list(session.exec(
        select(RolloutBatchRun).where(RolloutBatchRun.batch_id == batch_id)
    ).all())
    assert len(found_runs) == 1
