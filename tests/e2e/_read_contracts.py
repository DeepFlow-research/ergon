"""Read-service contract helpers for smoke E2Es."""

from __future__ import annotations

from uuid import UUID

from ergon_core.core.api.schemas import RunSnapshotDto
from ergon_core.core.runtime.services.run_read_service import RunReadService


def require_run_snapshot(run_id: UUID) -> RunSnapshotDto:
    snapshot = RunReadService().build_run_snapshot(run_id)
    assert snapshot is not None, f"RunReadService returned no snapshot for run {run_id}"
    return snapshot
