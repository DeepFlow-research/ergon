"""OpenRLHF agent_func adapter that calls Ergon's HTTP API.

Usage::

    # OpenRLHF CLI:
    --agent_func_path ergon_infra/adapters/openrlhf_http.py
    --agent_func_kwargs '{"ergon_url": "http://macbook:9000/api", "experiment_id": "<uuid>"}'
"""

import asyncio
import logging
import time
from typing import Protocol

import httpx

logger = logging.getLogger(__name__)

_client: httpx.AsyncClient | None = None
_experiment_id: str = ""
_sampler: str = "random"
_candidate_pool_size: int | None = None
_poll_interval_s: float = 2.0
_timeout_s: float = 300.0


class OpenRLHFCallbackContext(Protocol):
    """Opaque callback argument supplied by OpenRLHF and unused by this adapter."""


def configure(
    ergon_url: str,
    experiment_id: str,
    sampler: str = "random",
    candidate_pool_size: int | None = None,
    poll_interval_s: float = 2.0,
    timeout_s: float = 300.0,
) -> None:
    """Module-level configuration (called by OpenRLHF before agent_func)."""
    global _client, _experiment_id, _sampler, _candidate_pool_size, _poll_interval_s, _timeout_s
    _client = httpx.AsyncClient(base_url=ergon_url, timeout=30.0)
    _experiment_id = experiment_id
    _sampler = sampler
    _candidate_pool_size = candidate_pool_size
    _poll_interval_s = poll_interval_s
    _timeout_s = timeout_s


async def agent_func(
    messages: list[dict],
    generate_fn: OpenRLHFCallbackContext,
    tokenizer: OpenRLHFCallbackContext,
) -> dict:
    """OpenRLHF-compatible agent function backed by Ergon's HTTP API.

    ``generate_fn`` and ``tokenizer`` are provided by OpenRLHF but unused —
    Ergon handles generation via its own vLLM and tokenizer.
    """
    if _client is None:
        raise RuntimeError("Call configure() before agent_func()")

    resp = await _client.post(
        f"/rollouts/experiments/{_experiment_id}/rollout-batches",
        json={
            "experimentId": _experiment_id,
            "k": 1,
            "sampler": _sampler,
            "samplerConfig": {},
            "candidatePoolSize": _candidate_pool_size,
        },
    )
    resp.raise_for_status()
    batch_id = resp.json()["batch_id"]

    deadline = time.monotonic() + _timeout_s
    while time.monotonic() < deadline:
        poll = await _client.get(f"/rollouts/{batch_id}")
        poll.raise_for_status()
        data = poll.json()

        if data["status"] == "complete":
            trajs = data["trajectories"]
            if not trajs:
                raise RuntimeError(f"Batch {batch_id} completed with 0 trajectories")
            t = trajs[0]
            return {
                "input_ids": t["prompt_ids"],
                "response_ids": t["completion_ids"],
                "logprobs": t["logprobs"],
                "reward": t["reward"],
            }

        if data["status"] == "failed":
            raise RuntimeError(f"Rollout failed: {data.get('failures', [])}")

        await asyncio.sleep(_poll_interval_s)

    raise TimeoutError(f"Rollout batch {batch_id} timed out")
