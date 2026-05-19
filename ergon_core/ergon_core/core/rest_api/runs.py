"""FastAPI router for persisted run-detail snapshots."""

from uuid import UUID

from ergon_core.core.application.read_models.models import (
    RunSnapshotDto,
)
from ergon_core.core.application.graph.models import GraphMutationRecordDto
from ergon_core.core.application.read_models.errors import ResourceTooLargeError
from ergon_core.core.application.read_models.runs import RunReadService
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter(prefix="/runs", tags=["runs"])


def build_run_snapshot(run_id: UUID) -> RunSnapshotDto | None:
    return RunReadService().build_run_snapshot(run_id)


@router.get("/{run_id}", response_model=RunSnapshotDto)
def get_run(run_id: UUID) -> RunSnapshotDto:
    """Get a persisted run-detail snapshot suitable for frontend hydration."""
    snapshot = build_run_snapshot(run_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return snapshot


@router.get("/{run_id}/mutations", response_model=list[GraphMutationRecordDto])
def get_mutations(run_id: UUID) -> list[GraphMutationRecordDto]:
    """Return the append-only mutation log for a run, ordered by sequence."""
    mutations = RunReadService().list_mutations(run_id)
    if mutations is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return mutations


@router.get("/{run_id}/resources/{resource_id}/content")
def get_resource_content(run_id: UUID, resource_id: UUID) -> FileResponse:
    """Stream the blob bytes for a RunResource."""
    try:
        blob = RunReadService().get_resource_blob(run_id, resource_id)
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
