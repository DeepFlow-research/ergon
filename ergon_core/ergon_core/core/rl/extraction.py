# ergon_core/ergon_core/core/rl/extraction.py
"""Per-agent trajectory extraction from RunContextEvent rows.

Reads the lossless per-event records and builds the flat
(prompt_ids, completion_ids, logprobs, env_mask, reward) tuples that
TRL and veRL consume for policy gradient training.

Token layout: flat interleaved completion_ids with env_mask marking
model tokens (1) vs environment tokens (0).
"""

import json
import logging
from collections import defaultdict
from typing import Protocol, runtime_checkable

from ergon_core.core.shared.context_parts import (
    AssistantTextPart,
    ContextPartChunkLog,
    SystemPromptPart,
    ThinkingPart,
    ToolCallPart,
    ToolResultPart,
    UserMessagePart,
)
from ergon_core.core.persistence.context.models import RunContextEvent
from ergon_core.core.rl.rewards import IndependentTaskReward, RewardStrategy
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


@runtime_checkable
class Tokenizer(Protocol):
    def encode(self, text: str, *, add_special_tokens: bool = ...) -> list[int]: ...


class AgentTrajectory(BaseModel):
    model_config = {"frozen": True}

    agent_id: str
    prompt_ids: list[int] = Field(default_factory=list)
    completion_ids: list[int] = Field(default_factory=list)
    logprobs: list[float] = Field(default_factory=list)
    env_mask: list[int] = Field(default_factory=list)
    reward: float = 0.0
    turns: int = 0


def extract_agent_trajectories(
    context_events: list[RunContextEvent],
    eval_scores: dict[str, float],
    tokenizer: Tokenizer,
    *,
    reward_strategy: RewardStrategy | None = None,
) -> list[AgentTrajectory]:
    """Build per-agent trajectories from context event rows.

    One AgentTrajectory per unique worker_binding_key.
    Events must be pre-ordered by (task_execution_id, sequence).
    """
    if reward_strategy is None:
        reward_strategy = IndependentTaskReward()

    by_worker: dict[str, list[RunContextEvent]] = defaultdict(list)
    for event in context_events:
        by_worker[event.worker_binding_key].append(event)

    trajectories: list[AgentTrajectory] = []

    for worker_key, events in by_worker.items():
        prompt_text = _build_prompt_text(events)
        prompt_ids = tokenizer.encode(prompt_text) if prompt_text else []

        completion_ids: list[int] = []
        logprobs: list[float] = []
        env_mask: list[int] = []
        execution_ids: set[str] = set()

        for event in events:
            parsed = event.parsed_payload()
            part = parsed.part
            execution_ids.add(str(event.task_execution_id))

            if isinstance(part, (SystemPromptPart, UserMessagePart)):
                continue  # prompt context — not in completion

            if isinstance(part, (AssistantTextPart, ToolCallPart, ThinkingPart)):
                token_ids = _get_token_ids(parsed, tokenizer)
                token_logprobs = _get_logprobs(parsed, len(token_ids))
                completion_ids.extend(token_ids)
                logprobs.extend(token_logprobs)
                env_mask.extend([1] * len(token_ids))

            elif isinstance(part, ToolResultPart):
                result_tokens = tokenizer.encode(part.content)
                completion_ids.extend(result_tokens)
                logprobs.extend([0.0] * len(result_tokens))
                env_mask.extend([0] * len(result_tokens))

        reward = reward_strategy.assign(worker_key, eval_scores, execution_ids=execution_ids)

        trajectories.append(
            AgentTrajectory(
                agent_id=worker_key,
                prompt_ids=prompt_ids,
                completion_ids=completion_ids,
                logprobs=logprobs,
                env_mask=env_mask,
                reward=reward,
                turns=_count_turns(events),
            )
        )

    return trajectories


def _build_prompt_text(events: list[RunContextEvent]) -> str:
    parts: list[str] = []
    for event in events:
        payload = event.parsed_payload()
        part = payload.part
        if isinstance(part, SystemPromptPart):
            parts.append(part.content)
        elif isinstance(part, UserMessagePart):
            parts.append(part.content)
        elif isinstance(part, (AssistantTextPart, ToolCallPart, ThinkingPart, ToolResultPart)):
            break
    return "\n\n".join(parts)


def _get_token_ids(parsed: ContextPartChunkLog, tokenizer: Tokenizer) -> list[int]:
    """Return token IDs for a model-generated event.

    Uses token_ids if present. Falls back to tokenising the part content.
    """
    if parsed.token_ids is not None:
        return parsed.token_ids
    part = parsed.part
    if isinstance(part, AssistantTextPart):
        return tokenizer.encode(part.content)
    if isinstance(part, ToolCallPart):
        return tokenizer.encode(json.dumps(part.args))
    if isinstance(part, ThinkingPart):
        return tokenizer.encode(part.content)
    raise ValueError(f"_get_token_ids called on non-model event: {type(parsed)}")


def _get_logprobs(parsed: ContextPartChunkLog, n_tokens: int) -> list[float]:
    """Return per-token logprob scalars, padding with 0.0 if unavailable."""
    lps = parsed.logprobs
    if lps is None:
        return [0.0] * n_tokens
    scalars = [lp.logprob for lp in lps]
    if len(scalars) < n_tokens:
        scalars.extend([0.0] * (n_tokens - len(scalars)))
    return scalars[:n_tokens]


def _count_turns(events: list[RunContextEvent]) -> int:
    seen: set[str] = set()
    for event in events:
        parsed = event.parsed_payload()
        if isinstance(parsed.part, (AssistantTextPart, ToolCallPart, ThinkingPart)):
            if parsed.turn_id is not None:
                seen.add(parsed.turn_id)
    return len(seen)
