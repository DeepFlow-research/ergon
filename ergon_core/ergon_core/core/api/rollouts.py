"""Rollout-as-a-Service HTTP endpoints.

Exposes ``RolloutService`` over HTTP so RL trainers on remote GPU nodes
can submit episode batches and retrieve trajectories without importing
any Ergon internals.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, HTTPException

from ergon_core.core.rl.rollout_service import RolloutService
from ergon_core.core.rl.rollout_types import (
    PollResponse,
    SubmitRequest,
    SubmitResponse,
    WeightSyncRequest,
    WeightSyncResponse,
)
from ergon_core.core.rl.vllm_manager import VLLMManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rollouts", tags=["rollouts"])

_service: RolloutService | None = None
_vllm_manager: VLLMManager | None = None


def init_service(
    service: RolloutService,
    vllm_manager: VLLMManager | None = None,
) -> None:
    """Called during app lifespan to set singletons."""
    global _service, _vllm_manager  # noqa: PLW0603
    _service = service
    _vllm_manager = vllm_manager


def _get_service() -> RolloutService:
    if _service is None:
        raise HTTPException(503, "RolloutService not initialized")
    return _service


@router.post("/submit", response_model=SubmitResponse, status_code=202)
def submit_rollout(request: SubmitRequest) -> SubmitResponse:
    """Start a batch of episodes. Returns immediately with batch_id."""
    return _get_service().submit(request)


@router.get("/{batch_id}", response_model=PollResponse)
def poll_rollout(batch_id: UUID) -> PollResponse:
    """Poll batch status. Returns trajectories when complete."""
    result = _get_service().poll(batch_id)
    if result is None:
        raise HTTPException(404, f"Batch {batch_id} not found")
    return result


@router.delete("/{batch_id}", status_code=204)
def cancel_rollout(batch_id: UUID) -> None:
    """Cancel a pending/running batch."""
    _get_service().cancel(batch_id)


@router.post("/sync-weights", response_model=WeightSyncResponse)
def sync_weights(request: WeightSyncRequest) -> WeightSyncResponse:
    """Restart vLLM with a new checkpoint (full-weight RFT).

    Blocks until the new vLLM process is healthy.
    """
    if _vllm_manager is None:
        raise HTTPException(
            501,
            "vLLM manager not configured. Set ERGON_VLLM_ENABLED=true "
            "to let Ergon manage a vLLM process.",
        )
    try:
        _vllm_manager.restart(request.checkpoint_path)
    except (RuntimeError, TimeoutError) as exc:
        logger.error("Weight sync failed: %s", exc)
        raise HTTPException(500, str(exc)) from exc

    return WeightSyncResponse(
        success=True,
        vllm_model_loaded=request.checkpoint_path,
    )
