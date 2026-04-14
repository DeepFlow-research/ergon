"""veRL AgentLoopBase adapter that calls Ergon's HTTP API.

Usage::

    # In veRL config:
    agent_loop: ergon
    agent_loop_kwargs:
      ergon_url: http://macbook:9000/api
      definition_id: <uuid>
"""

import logging
import time

import httpx

logger = logging.getLogger(__name__)

try:
    from verl.experimental.agent_loop import AgentLoopBase, AgentLoopOutput, register

    @register("ergon")
    class ErgonAgentLoop(AgentLoopBase):
        """veRL agent loop backed by Ergon's Rollout-as-a-Service API."""

        def __init__(
            self,
            ergon_url: str,
            definition_id: str,
            poll_interval_s: float = 2.0,
            timeout_s: float = 300.0,
            **kwargs: object,
        ) -> None:
            super().__init__(**kwargs)
            self._client = httpx.AsyncClient(base_url=ergon_url, timeout=30.0)
            self._definition_id = definition_id
            self._poll_interval_s = poll_interval_s
            self._timeout_s = timeout_s

        async def run(self, sampling_params: dict, **kwargs: object) -> AgentLoopOutput:
            resp = await self._client.post(
                "/rollouts/submit",
                json={
                    "definition_id": self._definition_id,
                    "num_episodes": 1,
                },
            )
            resp.raise_for_status()
            batch_id = resp.json()["batch_id"]

            deadline = time.monotonic() + self._timeout_s
            while time.monotonic() < deadline:
                poll = await self._client.get(f"/rollouts/{batch_id}")
                poll.raise_for_status()
                data = poll.json()

                if data["status"] == "complete":
                    trajs = data["trajectories"]
                    if not trajs:
                        raise RuntimeError(f"Batch {batch_id} completed with 0 trajectories")
                    t = trajs[0]
                    return AgentLoopOutput(
                        prompt_ids=t["prompt_ids"],
                        response_ids=t["completion_ids"],
                        response_mask=t["env_mask"],
                        response_logprobs=t["logprobs"],
                        num_turns=t["num_turns"],
                        metrics={"reward": t["reward"]},
                    )

                if data["status"] == "failed":
                    raise RuntimeError(f"Rollout failed: {data.get('failures', [])}")

                # reason: asyncio is stdlib but imported locally to keep module-level imports minimal
                import asyncio

                await asyncio.sleep(self._poll_interval_s)

            raise TimeoutError(f"Rollout batch {batch_id} timed out")

except ImportError:
    logger.debug("veRL not installed; ErgonAgentLoop will not be registered")
