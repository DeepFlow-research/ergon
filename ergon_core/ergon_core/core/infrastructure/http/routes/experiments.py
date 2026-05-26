"""Experiment lifecycle API routes."""

from uuid import UUID

from ergon_core.core.application.experiments.service import (
    run_experiment as _run_experiment,
)
from ergon_core.core.views.experiments.models import (
    ExperimentDetailView,
    ExperimentListView,
    ExperimentSamplesView,
    SamplerInvocationsView,
)
from ergon_core.core.views.experiments.service import ExperimentReadService
from ergon_core.core.application.experiments.models import (
    ExperimentRunRequest,
    ExperimentRunResult,
)
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/experiments", tags=["experiments"])


@router.get("", response_model=ExperimentListView)
def list_experiments(limit: int = 50) -> ExperimentListView:
    return ExperimentReadService().list_experiment_states(limit=limit)


@router.get("/{experiment_id}", response_model=ExperimentDetailView)
def get_experiment(experiment_id: UUID) -> ExperimentDetailView:
    detail = ExperimentReadService().get_experiment_state(experiment_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Experiment {experiment_id} not found")
    return detail


@router.get("/{experiment_id}/samples", response_model=ExperimentSamplesView)
def get_experiment_samples(experiment_id: UUID) -> ExperimentSamplesView:
    samples = ExperimentReadService().list_experiment_samples(experiment_id)
    if samples is None:
        raise HTTPException(status_code=404, detail=f"Experiment {experiment_id} not found")
    return samples


@router.get("/{experiment_id}/sampler-invocations", response_model=SamplerInvocationsView)
def get_experiment_sampler_invocations(experiment_id: UUID) -> SamplerInvocationsView:
    invocations = ExperimentReadService().list_sampler_invocations(experiment_id)
    if invocations is None:
        raise HTTPException(status_code=404, detail=f"Experiment {experiment_id} not found")
    return invocations


@router.post("/{definition_id}/run", response_model=ExperimentRunResult, status_code=202)
async def run_experiment(
    definition_id: UUID, request: ExperimentRunRequest | None = None
) -> ExperimentRunResult:
    launch_request = request or ExperimentRunRequest(definition_id=definition_id)
    if launch_request.definition_id != definition_id:
        raise HTTPException(status_code=400, detail="definition_id mismatch")
    return await _run_experiment(launch_request)
