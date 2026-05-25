"""FastAPI router for persisted sample-detail snapshots."""

from uuid import UUID

from ergon_core.core.views.samples.models import (
    SampleSummaryDto,
    SampleSnapshotDto,
)
from ergon_core.core.application.samples.events import SampleRuntimeEventView
from ergon_core.core.views.errors import ResourceTooLargeError
from ergon_core.core.views.samples.service import SampleSnapshotReadService
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter(prefix="/samples", tags=["samples"])


@router.get("", response_model=list[SampleSummaryDto])
def list_samples(
    limit: int = 20,
    status: str | None = None,
    definition_id: UUID | None = None,
    experiment: str | None = None,
    offset: int = 0,
) -> list[SampleSummaryDto]:
    """List persisted sample summaries for dashboard indexes."""
    return SampleSnapshotReadService().list_samples(
        limit=limit,
        status=status,
        definition_id=definition_id,
        experiment=experiment,
        offset=offset,
    )


@router.get("/{sample_id}", response_model=SampleSnapshotDto)
def get_sample_snapshot(sample_id: UUID) -> SampleSnapshotDto:
    """Get a persisted sample-detail snapshot suitable for frontend hydration."""
    snapshot = SampleSnapshotReadService().build_snapshot(sample_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail=f"Sample {sample_id} not found")
    return snapshot


@router.get("/{sample_id}/events", response_model=list[SampleRuntimeEventView])
def get_sample_runtime_events(sample_id: UUID) -> list[SampleRuntimeEventView]:
    """Return the typed append-only runtime event stream for a sample."""
    events = SampleSnapshotReadService().list_events(sample_id)
    if events is None:
        raise HTTPException(status_code=404, detail=f"Sample {sample_id} not found")
    return events


@router.get("/{sample_id}/resources/{resource_id}/content")
def get_resource_content(sample_id: UUID, resource_id: UUID) -> FileResponse:
    """Stream the blob bytes for a SampleResource."""
    try:
        blob = SampleSnapshotReadService().get_resource_blob(sample_id, resource_id)
    except (FileNotFoundError, OSError) as e:
        raise HTTPException(status_code=404, detail="Resource blob missing on disk") from e
    except ResourceTooLargeError as e:
        raise HTTPException(status_code=413, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=404, detail="Resource blob outside blob root") from e

    if blob is None:
        raise HTTPException(status_code=404, detail=f"Resource {resource_id} not found")

    return FileResponse(
        path=blob.path,
        media_type=blob.media_type,
        filename=blob.filename,
        content_disposition_type="inline",
    )
