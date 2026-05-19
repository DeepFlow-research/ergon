"""Experiment lifecycle API routes."""

from uuid import UUID

from ergon_core.core.application.experiments.service import (
    run_experiment as _run_experiment,
)
from ergon_core.core.views.experiments.models import (
    ExperimentDetailDto,
    ExperimentSummaryDto,
)
from ergon_core.core.views.experiments.service import ExperimentReadService
from ergon_core.core.application.experiments.models import (
    ExperimentRunRequest,
    ExperimentRunResult,
)
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/experiments", tags=["experiments"])


@router.get("", response_model=list[ExperimentSummaryDto])
def list_experiments(limit: int = 50) -> list[ExperimentSummaryDto]:
    return ExperimentReadService().list_experiments(limit=limit)


@router.get("/{definition_id}", response_model=ExperimentDetailDto)
def get_experiment(definition_id: UUID) -> ExperimentDetailDto:
    detail = ExperimentReadService().get_experiment(definition_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Experiment {definition_id} not found")
    return detail


@router.post("/{definition_id}/run", response_model=ExperimentRunResult, status_code=202)
async def run_experiment(
    definition_id: UUID, request: ExperimentRunRequest | None = None
) -> ExperimentRunResult:
    launch_request = request or ExperimentRunRequest(definition_id=definition_id)
    if launch_request.definition_id != definition_id:
        raise HTTPException(status_code=400, detail="definition_id mismatch")
    return await _run_experiment(launch_request)
