"""Run identity helpers owned by the runtime layer."""

from __future__ import annotations

from uuid import UUID

from ergon_core.core.application.runtime.task_errors import SampleRecordMissingError
from ergon_core.core.persistence.telemetry.models import SampleRecord
from sqlmodel import Session, select


def definition_id_for_run(session: Session, sample_id: UUID) -> UUID | None:
    """Return the definition id for a run or fail the runtime invariant loudly."""
    run = session.exec(select(SampleRecord).where(SampleRecord.id == sample_id)).first()
    if run is None:
        raise SampleRecordMissingError(sample_id)
    return run.definition_id
