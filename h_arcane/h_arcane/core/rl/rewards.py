"""Reward strategies for per-agent credit assignment.

In multi-agent DAG benchmarks, the overall episode reward must be
decomposed into per-agent rewards.  These strategies define how that
decomposition works.
"""

from statistics import mean
from typing import Protocol

from h_arcane.core.persistence.telemetry.models import RunGenerationTurn


class RewardStrategy(Protocol):
    """Assigns a scalar reward to one agent given the episode data."""

    def assign(
        self,
        agent_id: str,
        turns: list[RunGenerationTurn],
        eval_scores: dict[str, float],
    ) -> float: ...


class IndependentTaskReward:
    """Each agent's reward = mean score of the tasks it worked on.

    Filters ``eval_scores`` to only the task executions this agent
    participated in (matched via ``task_execution_id``).
    """

    def assign(
        self,
        agent_id: str,
        turns: list[RunGenerationTurn],
        eval_scores: dict[str, float],
    ) -> float:
        agent_execution_ids = {str(t.task_execution_id) for t in turns}
        agent_scores = [score for key, score in eval_scores.items() if key in agent_execution_ids]
        return mean(agent_scores) if agent_scores else 0.0


class SharedEpisodeReward:
    """All agents share the overall episode score equally."""

    def assign(
        self,
        agent_id: str,
        turns: list[RunGenerationTurn],
        eval_scores: dict[str, float],
    ) -> float:
        if not eval_scores:
            return 0.0
        return mean(eval_scores.values())
