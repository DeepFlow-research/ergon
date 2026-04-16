"""DEPRECATED: in-process TRL rollout_func adapter.

This module is a thin wrapper around ``RolloutService`` that provides the
``rollout_func(prompts, trainer) -> dict`` interface TRL expects. It will
be deleted once the HTTP adapter (``ergon_infra/adapters/trl_http.py``)
is the sole code path.

For new code, use the HTTP API (``POST /rollouts/submit``) instead.
"""

import logging
import time
from collections.abc import Callable
from uuid import UUID

import inngest as inngest_lib
from ergon_core.core.rl.extraction import Tokenizer
from ergon_core.core.rl.rewards import RewardStrategy
from ergon_core.core.rl.rollout_service import RolloutService
from ergon_core.core.rl.rollout_types import BatchStatus, SubmitRequest
from sqlmodel import Session

logger = logging.getLogger(__name__)

PromptInput = str | list[dict[str, object]]


def make_ergon_rollout_func(
    *,
    definition_id: UUID,
    inngest_send: Callable[[inngest_lib.Event], None],
    session_factory: Callable[[], Session],
    tokenizer: Tokenizer,
    reward_strategy: RewardStrategy | None = None,
    timeout_s: float = 300.0,
    poll_interval_s: float = 1.0,
) -> Callable[[list[PromptInput], object], dict[str, object]]:
    """Create a TRL-compatible ``rollout_func`` backed by ``RolloutService``.

    DEPRECATED: prefer the HTTP adapter for remote training. This in-process
    path exists for backward compatibility during the migration.
    """
    service = RolloutService(
        session_factory=session_factory,
        inngest_send=inngest_send,
        tokenizer_name=tokenizer.name_or_path,  # type: ignore[attr-defined]
        reward_strategy=reward_strategy,
    )

    def rollout_func(
        prompts: list[PromptInput],
        trainer: object,
    ) -> dict[str, object]:
        batch = service.submit(
            SubmitRequest(
                definition_id=definition_id,
                num_episodes=len(prompts),
            )
        )

        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            result = service.poll(batch.batch_id)
            if result is None:
                raise RuntimeError(f"Batch {batch.batch_id} disappeared")

            if result.status == BatchStatus.COMPLETE:
                return {
                    "prompt_ids": [t.prompt_ids for t in result.trajectories],
                    "completion_ids": [t.completion_ids for t in result.trajectories],
                    "logprobs": [t.logprobs for t in result.trajectories],
                    "completion_reward": [t.reward for t in result.trajectories],
                    "env_mask": [t.env_mask for t in result.trajectories],
                }

            if result.status == BatchStatus.FAILED:
                raise RuntimeError(f"Rollout batch {batch.batch_id} failed: {result.failures}")

            time.sleep(poll_interval_s)

        service.cancel(batch.batch_id)
        raise TimeoutError(f"Rollout batch {batch.batch_id} timed out after {timeout_s}s")

    return rollout_func
