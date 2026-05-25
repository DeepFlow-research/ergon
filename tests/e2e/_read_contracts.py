"""Read-service contract helpers for smoke E2Es."""

from __future__ import annotations

from uuid import UUID

from ergon_core.core.views.samples.models import SampleSnapshotDto
from ergon_core.core.views.samples.service import SampleSnapshotReadService


def require_run_snapshot(sample_id: UUID) -> SampleSnapshotDto:
    snapshot = SampleSnapshotReadService().build_snapshot(sample_id)
    assert snapshot is not None, (
        f"SampleSnapshotReadService returned no snapshot for sample {sample_id}"
    )
    return snapshot
