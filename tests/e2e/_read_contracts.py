"""Read-service contract helpers for smoke E2Es."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from ergon_core.core.views.samples.models import SampleSnapshotDto


def require_run_snapshot(sample_id: UUID) -> SampleSnapshotDto:
    from ergon_core.core.views.samples.service import SampleSnapshotReadService

    snapshot = SampleSnapshotReadService().build_snapshot(sample_id)
    assert snapshot is not None, (
        f"SampleSnapshotReadService returned no snapshot for sample {sample_id}"
    )
    return snapshot
