"""TRL rollout_func adapter that calls Ergon's HTTP API.

This is the ONLY file the GPU node needs from ergon_infra (plus httpx).
No ergon_core, no inngest, no sqlmodel, no Postgres.

Usage::

    from ergon_infra.adapters.trl_http import make_ergon_http_rollout_func

    rollout_func = make_ergon_http_rollout_func(
        ergon_url="http://macbook:9000/api",
        definition_id="<uuid>",
    )
    trainer = GRPOTrainer(..., rollout_func=rollout_func)
"""

import logging
import time
from typing import Protocol, TypedDict

import httpx

logger = logging.getLogger(__name__)


class RolloutBatch(TypedDict):
    """Batch tensors returned by :func:`rollout_func` for GRPOTrainer."""

    prompt_ids: list[list[int]]
    completion_ids: list[list[int]]
    logprobs: list[list[float]]
    completion_reward: list[float]
    env_mask: list[list[int]]


class TRLTrainerContext(Protocol):
    """Opaque trainer callback argument supplied by TRL and unused here."""


def make_ergon_http_rollout_func(
    ergon_url: str,
    definition_id: str,
    poll_interval_s: float = 2.0,
    timeout_s: float = 300.0,
):
    """Create a TRL-compatible ``rollout_func`` backed by Ergon's HTTP API.

    Args:
        ergon_url: base URL of the Ergon API (e.g. ``http://localhost:9000/api``).
        definition_id: ExperimentDefinition UUID to run episodes against.
        poll_interval_s: seconds between poll requests.
        timeout_s: max wall-clock seconds to wait for a batch to complete.

    Returns:
        A ``rollout_func(prompts, trainer) -> dict`` for ``GRPOTrainer``.
    """
    client = httpx.Client(base_url=ergon_url, timeout=30.0)

    def rollout_func(prompts: list, trainer: TRLTrainerContext) -> RolloutBatch:
        resp = client.post(
            "/rollouts/submit",
            json={
                "definition_id": definition_id,
                "num_episodes": len(prompts),
            },
        )
        resp.raise_for_status()
        batch_id = resp.json()["batch_id"]
        logger.info("Submitted rollout batch %s (%d episodes)", batch_id, len(prompts))

        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            poll = client.get(f"/rollouts/{batch_id}")
            poll.raise_for_status()
            data = poll.json()

            if data["status"] == "complete":
                trajs = data["trajectories"]
                logger.info(
                    "Batch %s complete: %d trajectories",
                    batch_id,
                    len(trajs),
                )
                return {
                    "prompt_ids": [t["prompt_ids"] for t in trajs],
                    "completion_ids": [t["completion_ids"] for t in trajs],
                    "logprobs": [t["logprobs"] for t in trajs],
                    "completion_reward": [t["reward"] for t in trajs],
                    "env_mask": [t["env_mask"] for t in trajs],
                }

            if data["status"] == "failed":
                raise RuntimeError(f"Rollout batch {batch_id} failed: {data.get('failures', [])}")

            logger.debug(
                "Batch %s: %d/%d complete",
                batch_id,
                data.get("completed", 0),
                data.get("total", 0),
            )
            time.sleep(poll_interval_s)

        client.delete(f"/rollouts/{batch_id}")
        raise TimeoutError(f"Rollout batch {batch_id} timed out after {timeout_s}s")

    return rollout_func
