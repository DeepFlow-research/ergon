"""Experiment lifecycle API routes."""

from uuid import UUID

from ergon_core.core.runtime.services.experiment_definition_service import (
    ExperimentDefinitionService,
)
from ergon_core.core.runtime.services.experiment_launch_service import ExperimentLaunchService
from ergon_core.core.runtime.services.experiment_read_service import (
    ExperimentDetailDto,
    ExperimentReadService,
    ExperimentSummaryDto,
)
from ergon_core.core.runtime.services.experiment_schemas import (
    ExperimentDefineRequest,
    ExperimentDefineResult,
    ExperimentRunRequest,
    ExperimentRunResult,
)
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/experiments", tags=["experiments"])


@router.get("", response_model=list[ExperimentSummaryDto])
def list_experiments(limit: int = 50) -> list[ExperimentSummaryDto]:
    return ExperimentReadService().list_experiments(limit=limit)


@router.get("/{experiment_id}", response_model=ExperimentDetailDto)
def get_experiment(experiment_id: UUID) -> ExperimentDetailDto:
    detail = ExperimentReadService().get_experiment(experiment_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Experiment {experiment_id} not found")
    return detail


@router.post("/define", response_model=ExperimentDefineResult, status_code=201)
def define_experiment(request: ExperimentDefineRequest) -> ExperimentDefineResult:
    return ExperimentDefinitionService().define_benchmark_experiment(request)


@router.post("/{experiment_id}/run", response_model=ExperimentRunResult, status_code=202)
async def run_experiment(experiment_id: UUID, request: ExperimentRunRequest | None = None):
    launch_request = request or ExperimentRunRequest(experiment_id=experiment_id)
    if launch_request.experiment_id != experiment_id:
        raise HTTPException(status_code=400, detail="experiment_id mismatch")
    return await ExperimentLaunchService().run_experiment(launch_request)
