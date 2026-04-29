"""Read-service contract helpers for smoke E2Es."""

from __future__ import annotations

from uuid import UUID

from ergon_core.core.application.read_models.models import RunSnapshotDto
from ergon_core.core.application.read_models.runs import RunReadService


def require_run_snapshot(run_id: UUID) -> RunSnapshotDto:
    snapshot = RunReadService().build_run_snapshot(run_id)
    assert snapshot is not None, f"RunReadService returned no snapshot for run {run_id}"
    return snapshot
