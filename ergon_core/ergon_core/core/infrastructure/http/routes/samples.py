"""FastAPI router for persisted sample-detail snapshots."""

from uuid import UUID

from ergon_core.core.views.samples.models import (
    SampleDetailView,
    SampleEventsView,
    SampleGraphView,
    SampleSummaryDto,
)
from ergon_core.core.views.errors import ResourceTooLargeError
from ergon_core.core.views.samples.service import SampleReadService, SampleSnapshotReadService
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


@router.get("/{sample_id}", response_model=SampleDetailView)
def get_sample_detail(sample_id: UUID) -> SampleDetailView:
    """Get persisted sample provenance and status details."""
    detail = SampleReadService().get_sample_detail(sample_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Sample {sample_id} not found")
    return detail


@router.get("/{sample_id}/events", response_model=SampleEventsView)
def get_sample_runtime_events(sample_id: UUID) -> SampleEventsView:
    """Return the typed append-only runtime event stream for a sample."""
    events = SampleReadService().list_sample_events(sample_id)
    if events is None:
        raise HTTPException(status_code=404, detail=f"Sample {sample_id} not found")
    return events


@router.get("/{sample_id}/graph", response_model=SampleGraphView)
def get_sample_graph(sample_id: UUID) -> SampleGraphView:
    """Return the sample graph projection."""
    graph = SampleReadService().get_sample_graph(sample_id)
    if graph is None:
        raise HTTPException(status_code=404, detail=f"Sample {sample_id} not found")
    return graph


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
