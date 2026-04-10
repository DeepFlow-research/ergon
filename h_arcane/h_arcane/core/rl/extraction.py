"""Per-agent trajectory extraction from RunGenerationTurn rows.

Reads the lossless per-turn records from the DB and builds the flat
``(prompt_ids, completion_ids, logprobs, env_mask, reward)`` tuples that
TRL and veRL consume for policy gradient training.

Token layout: flat interleaved ``completion_ids`` with ``env_mask``
marking model tokens (1) vs environment tokens (0).  TRL v1.0 supports
this via its ``env_mask`` / ``tool_mask`` mechanism.
"""

import logging
from collections import defaultdict
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field

from h_arcane.core.persistence.telemetry.models import RunGenerationTurn
from h_arcane.core.rl.rewards import IndependentTaskReward, RewardStrategy

logger = logging.getLogger(__name__)


@runtime_checkable
class Tokenizer(Protocol):
    """Minimal interface required by trajectory extraction."""

    def encode(self, text: str, *, add_special_tokens: bool = ...) -> list[int]: ...


class AgentTrajectory(BaseModel):
    """One agent's causal step sequence extracted from the episode."""

    model_config = {"frozen": True}

    agent_id: str
    prompt_ids: list[int] = Field(default_factory=list)
    completion_ids: list[int] = Field(default_factory=list)
    logprobs: list[float] = Field(default_factory=list)
    env_mask: list[int] = Field(default_factory=list)
    reward: float = 0.0
    turns: int = 0


def extract_agent_trajectories(
    generation_turns: list[RunGenerationTurn],
    eval_scores: dict[str, float],
    tokenizer: Tokenizer,
    *,
    prompt_text: str | None = None,
    reward_strategy: RewardStrategy | None = None,
) -> list[AgentTrajectory]:
    """Build per-agent trajectories from generation turn DB rows.

    For single-agent benchmarks the result is one trajectory.
    For multi-agent DAGs, one trajectory per worker binding key.

    Args:
        generation_turns: ``RunGenerationTurn`` rows for one run, ordered
            by ``(task_execution_id, turn_index)``.
        eval_scores: mapping of ``task_execution_id -> score``.
        tokenizer: a HuggingFace-compatible tokenizer with ``.encode(text)``.
        prompt_text: the initial prompt / task description, tokenized as ``prompt_ids``,
            or *None* to skip.  TRL needs this for KL divergence computation.
        reward_strategy: how to assign per-agent rewards.  Defaults to
            ``IndependentTaskReward``.
    """
    if reward_strategy is None:
        reward_strategy = IndependentTaskReward()

    turns_by_agent: dict[str, list[RunGenerationTurn]] = defaultdict(list)
    for turn in generation_turns:
        turns_by_agent[turn.worker_binding_key].append(turn)

    prompt_ids_shared: list[int] = tokenizer.encode(prompt_text) if prompt_text else []

    trajectories: list[AgentTrajectory] = []

    for agent_id, agent_turns in turns_by_agent.items():
        prompt_ids: list[int] = list(prompt_ids_shared)
        completion_ids: list[int] = []
        logprobs: list[float] = []
        env_mask: list[int] = []
        turn_count = 0

        for turn in agent_turns:
            stored_logprobs = turn.logprobs_json
            if isinstance(stored_logprobs, list) and stored_logprobs:
                for lp in stored_logprobs:
                    if not isinstance(lp, dict):
                        continue
                    token_str = lp.get("token", "")
                    if not token_str:
                        continue
                    ids = tokenizer.encode(token_str, add_special_tokens=False)
                    if len(ids) != 1:
                        logger.warning(
                            "Token %r re-tokenized to %d IDs (expected 1) — "
                            "logprob alignment may be wrong",
                            token_str, len(ids),
                        )
                    completion_ids.extend(ids)
                    logprobs.extend([lp.get("logprob", 0.0)] * len(ids))
                    env_mask.extend([1] * len(ids))
            elif turn.response_text:
                tokens = tokenizer.encode(turn.response_text)
                completion_ids.extend(tokens)
                logprobs.extend([0.0] * len(tokens))
                env_mask.extend([1] * len(tokens))

            for tr in turn.tool_results_json or []:
                result_text = str(tr.get("result", ""))
                if result_text:
                    env_tokens = tokenizer.encode(result_text)
                    completion_ids.extend(env_tokens)
                    logprobs.extend([0.0] * len(env_tokens))
                    env_mask.extend([0] * len(env_tokens))

            turn_count += 1

        reward = reward_strategy.assign(agent_id, agent_turns, eval_scores)

        trajectories.append(AgentTrajectory(
            agent_id=agent_id,
            prompt_ids=prompt_ids,
            completion_ids=completion_ids,
            logprobs=logprobs,
            env_mask=env_mask,
            reward=reward,
            turns=turn_count,
        ))

    return trajectories
