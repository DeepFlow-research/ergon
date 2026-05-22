"""Run identity helpers owned by the runtime layer."""

from __future__ import annotations

from uuid import UUID

from ergon_core.core.application.runtime.task_errors import RunRecordMissingError
from ergon_core.core.persistence.telemetry.models import RunRecord
from sqlmodel import Session, select


def definition_id_for_run(session: Session, run_id: UUID) -> UUID:
    """Return the definition id for a run or fail the runtime invariant loudly."""
    run = session.exec(select(RunRecord).where(RunRecord.id == run_id)).first()
    if run is None:
        raise RunRecordMissingError(run_id)
    return run.definition_id
