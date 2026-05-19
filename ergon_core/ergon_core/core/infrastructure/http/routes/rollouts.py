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
    SubmitRequest,
    SubmitResponse,
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


@router.post("/submit", response_model=SubmitResponse, status_code=202)
def submit_rollout(
    request: SubmitRequest,
    service: Annotated[RolloutService, Depends(get_rollout_service)],
) -> SubmitResponse:
    """Start a batch of episodes. Returns immediately with batch_id."""
    return service.submit(request)


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
