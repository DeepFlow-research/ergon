"""Experiment lifecycle API routes."""

from uuid import UUID

from ergon_core.core.views.experiments.models import (
    ExperimentDetailView,
    ExperimentListView,
    ExperimentSamplesView,
    SamplerInvocationsView,
)
from ergon_core.core.views.experiments.service import ExperimentReadService
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
