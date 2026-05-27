"""Rollout-as-a-Service HTTP endpoints.

Exposes ``RolloutService`` over HTTP so RL trainers on remote GPU nodes
can submit episode batches and retrieve trajectories without importing
any Ergon internals.
"""

import logging
from typing import Annotated, cast
from uuid import UUID

from ergon_core.core.rl.rollout_service import RolloutService
from ergon_core.core.rl.rollout_types import (
    PollResponse,
    RolloutBatchSummary,
    TrainingRolloutRequest,
    WeightSyncRequest,
    WeightSyncResponse,
)
from ergon_core.core.rl.vllm_manager import VLLMManager
from fastapi import APIRouter, Depends, HTTPException, Request

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rollouts", tags=["rollouts"])


def get_rollout_service(request: Request) -> RolloutService:
    try:
        service = request.app.state.rollout_service
    except AttributeError:
        raise HTTPException(503, "RolloutService not initialized")
    return cast(RolloutService, service)


def get_vllm_manager(request: Request) -> VLLMManager | None:
    try:
        manager = request.app.state.vllm_manager
    except AttributeError:
        return None
    return cast(VLLMManager, manager)


@router.post(
    "/experiments/{experiment_id}/rollout-batches",
    response_model=RolloutBatchSummary,
    status_code=202,
)
async def submit_experiment_rollout_batch(
    experiment_id: UUID,
    request: TrainingRolloutRequest,
    service: Annotated[RolloutService, Depends(get_rollout_service)],
) -> RolloutBatchSummary:
    """Start a trainer batch from a persisted experiment candidate pool."""
    if request.experiment_id != experiment_id:
        raise HTTPException(400, "experiment_id mismatch")
    try:
        return await service.submit_experiment_batch(request)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/{batch_id}", response_model=PollResponse)
def poll_rollout(
    batch_id: UUID,
    service: Annotated[RolloutService, Depends(get_rollout_service)],
) -> PollResponse:
    """Poll batch status. Returns trajectories when complete."""
    result = service.poll(batch_id)
    if result is None:
        raise HTTPException(404, f"Batch {batch_id} not found")
    return result


@router.get("/batches/{batch_id}", response_model=RolloutBatchSummary)
def get_rollout_batch(
    batch_id: UUID,
    service: Annotated[RolloutService, Depends(get_rollout_service)],
) -> RolloutBatchSummary:
    """Load durable trainer batch membership by sample id."""
    result = service.get_rollout_batch_by_id(batch_id)
    if result is None:
        raise HTTPException(404, f"Batch {batch_id} not found")
    return result


@router.delete("/{batch_id}", status_code=204)
def cancel_rollout(
    batch_id: UUID,
    service: Annotated[RolloutService, Depends(get_rollout_service)],
) -> None:
    """Cancel a pending/running batch."""
    service.cancel(batch_id)


@router.post("/sync-weights", response_model=WeightSyncResponse)
def sync_weights(
    request: WeightSyncRequest,
    vllm_manager: Annotated[VLLMManager | None, Depends(get_vllm_manager)],
) -> WeightSyncResponse:
    """Restart vLLM with a new checkpoint (full-weight RFT).

    Blocks until the new vLLM process is healthy.
    """
    if vllm_manager is None:
        raise HTTPException(
            501,
            "vLLM manager not configured. Set ERGON_VLLM_ENABLED=true "
            "to let Ergon manage a vLLM process.",
        )
    try:
        vllm_manager.restart(request.checkpoint_path)
    except (RuntimeError, TimeoutError) as exc:
        logger.error("Weight sync failed: %s", exc)
        raise HTTPException(500, str(exc)) from exc

    return WeightSyncResponse(
        success=True,
        vllm_model_loaded=request.checkpoint_path,
    )
