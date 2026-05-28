"""TRL rollout_func adapter that calls Ergon's HTTP API.

This is the ONLY file the GPU node needs from ergon_infra (plus httpx).
No ergon_core, no inngest, no sqlmodel, no Postgres.

Usage::

    from ergon_infra.adapters.trl_http import make_ergon_http_rollout_func

    rollout_func = make_ergon_http_rollout_func(
        ergon_url="http://macbook:9000/api",
        experiment_id="<uuid>",
    )
    trainer = GRPOTrainer(..., rollout_func=rollout_func)
"""

import logging
import time
from collections.abc import Callable
from typing import Any, Protocol, TypedDict, cast

import httpx

logger = logging.getLogger(__name__)


class RolloutBatch(TypedDict):
    """Batch tensors returned by :func:`rollout_func` for GRPOTrainer."""

    prompt_ids: list[list[int]]
    completion_ids: list[list[int]]
    logprobs: list[list[float]]
    completion_reward: list[float]
    trace_metadata: list[dict]


class TRLTrainerContext(Protocol):
    """Opaque trainer callback argument supplied by TRL and unused here."""


def make_ergon_http_rollout_func(
    ergon_url: str,
    experiment_id: str,
    sampler: str = "random",
    candidate_pool_size: int | None = None,
    poll_interval_s: float = 2.0,
    timeout_s: float = 300.0,
) -> Callable[[list, TRLTrainerContext], "RolloutBatch"]:
    """Create a TRL-compatible ``rollout_func`` backed by Ergon's HTTP API.

    Args:
        ergon_url: base URL of the Ergon API (e.g. ``http://localhost:9000/api``).
        experiment_id: persisted experiment UUID to sample from.
        poll_interval_s: seconds between poll requests.
        timeout_s: max wall-clock seconds to wait for a batch to complete.

    Returns:
        A ``rollout_func(prompts, trainer) -> dict`` for ``GRPOTrainer``.
    """
    client = httpx.Client(base_url=ergon_url, timeout=30.0)

    def rollout_func(prompts: list, trainer: TRLTrainerContext) -> RolloutBatch:
        resp = client.post(
            f"/rollouts/experiments/{experiment_id}/rollout-batches",
            json={
                "experimentId": experiment_id,
                "k": len(prompts),
                "sampler": sampler,
                "samplerConfig": {},
                "candidatePoolSize": candidate_pool_size,
            },
        )
        resp.raise_for_status()
        submit_data = resp.json()
        batch_id = submit_data.get("batchId") or submit_data.get("batch_id")
        if batch_id is None:
            raise RuntimeError("Rollout submit response missing batchId")
        logger.info("Submitted rollout batch %s (%d episodes)", batch_id, len(prompts))

        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            poll = client.get(f"/rollouts/{batch_id}")
            poll.raise_for_status()
            data = poll.json()

            if data["status"] == "complete":
                records = data.get("trainingRecords")
                if records is None:
                    raise RuntimeError("Rollout poll response missing trainingRecords")
                logger.info(
                    "Batch %s complete: %d training records",
                    batch_id,
                    len(records),
                )
                return {
                    "prompt_ids": [
                        _get_int_list(record, "promptIds", "prompt_ids") for record in records
                    ],
                    "completion_ids": [
                        _get_int_list(record, "completionIds", "completion_ids")
                        for record in records
                    ],
                    "logprobs": [cast(list[float], record["logprobs"]) for record in records],
                    "completion_reward": [cast(float, record["reward"]) for record in records],
                    "trace_metadata": [
                        {
                            "sampleId": _get(record, "sampleId", "sample_id"),
                            "actor": record["actor"],
                            "taskId": record.get("taskId") or record.get("task_id"),
                            "taskAttemptId": record.get("taskAttemptId")
                            or record.get("task_attempt_id"),
                        }
                        for record in records
                    ],
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


def _get(data: dict[str, Any], camel: str, snake: str) -> object:
    if camel in data:
        return data[camel]
    return data[snake]


def _get_int_list(data: dict[str, Any], camel: str, snake: str) -> list[int]:
    return cast(list[int], _get(data, camel, snake))
