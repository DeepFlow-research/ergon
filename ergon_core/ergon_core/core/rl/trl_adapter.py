"""TRL ``rollout_func`` adapter for GRPOTrainer.

Bridges Ergon's Inngest-orchestrated environment plane to TRL's training
loop.  The rollout_func:

1. Creates RunRecord rows for a batch of episodes
2. Fires ``workflow/started`` Inngest events to the Inngest server
3. Polls Postgres until all episodes complete
4. Reads ``RunGenerationTurn`` rows (with logprobs) and ``RunTaskEvaluation`` scores
5. Extracts per-agent trajectories
6. Returns ``{prompt_ids, completion_ids, logprobs, completion_reward, env_mask}``

The entire Inngest pipeline (DAG orchestration, sandbox execution, rubric
evaluation) runs unchanged.  This adapter is the thin bridge.

IMPORTANT — network topology: this function runs IN-PROCESS on whatever
machine TRL is running on (typically the GPU node). It makes outbound
HTTP calls to Inngest and TCP connections to Postgres, which may be on
a different machine (e.g. your MacBook via Tailscale). The Inngest
workers that execute episodes also run on that other machine, and they
call back to vLLM on the GPU node's public IP for model generation.

This cross-machine round-trip is a consequence of TRL's in-process
rollout_func API. A cleaner architecture would have the environment
orchestrator (MacBook) drive the loop and send trajectories to the
GPU for gradient computation — see veRL's Ray-based AgentLoopBase
for that pattern.

The abstraction that would fix this in TRL: a RolloutService protocol
with submit/poll semantics instead of a synchronous callback::

    class RolloutService(Protocol):
        def submit(self, prompts, policy_version) -> batch_id: ...
        def poll(self, batch_id) -> RolloutResult | None: ...

The environment writes completed trajectories to an external buffer
(Redis, Postgres, HTTP). The trainer reads from it. Neither side
needs to reach the other's internal services. This also enables async
GRPO for free — the trainer submits batch N+1 while computing
gradients for batch N, using policy_version for importance sampling.

TRL's planned async GRPO uses an in-process buffer which does NOT
fix the co-location requirement. Externalising the buffer is the
key change that would decouple environment from trainer.

Usage::

    from ergon_core.core.rl.trl_adapter import make_ergon_rollout_func

    rollout_func = make_ergon_rollout_func(
        definition_id=def_id,
        inngest_send=inngest_client.send_sync,
        session_factory=get_session,
        tokenizer=tokenizer,
    )

    trainer = GRPOTrainer(
        model="Qwen/Qwen2.5-7B",
        rollout_func=rollout_func,
        ...
    )
"""

import logging
from collections import defaultdict
from collections.abc import Callable
from uuid import UUID

import inngest as inngest_lib
from sqlmodel import Session, select

from ergon_core.core.persistence.shared.enums import RunStatus
from ergon_core.core.persistence.shared.ids import new_id
from ergon_core.core.persistence.telemetry.models import (
    RunGenerationTurn,
    RunRecord,
    RunTaskEvaluation,
)
from ergon_core.core.rl.extraction import Tokenizer, extract_agent_trajectories
from ergon_core.core.rl.polling import poll_until_all_complete
from ergon_core.core.rl.rewards import IndependentTaskReward, RewardStrategy
from ergon_core.core.runtime.events.task_events import WorkflowStartedEvent
from ergon_core.core.persistence.telemetry.models import RunTaskExecution

logger = logging.getLogger(__name__)

InngestSend = Callable[[inngest_lib.Event], None]
SessionFactory = Callable[[], Session]
# TRL may pass plain strings or chat-template dict lists per prompt.
PromptInput = str | list[dict[str, object]]


def make_ergon_rollout_func(
    *,
    definition_id: UUID,
    inngest_send: InngestSend,
    session_factory: SessionFactory,
    tokenizer: Tokenizer,
    reward_strategy: RewardStrategy | None = None,
    timeout_s: float = 300.0,
    poll_interval_s: float = 1.0,
) -> Callable[[list[PromptInput], object], dict[str, object]]:
    """Create a TRL-compatible ``rollout_func``.

    Network requirements: ``inngest_send`` and ``session_factory`` must
    be able to reach the Inngest server and Postgres respectively. When
    training runs on a remote GPU node, this typically means Tailscale
    or a cloud-hosted stack. The returned function is called in-process
    by TRL on whatever machine the trainer runs on.

    Args:
        definition_id: the persisted ``ExperimentDefinition.id`` to run episodes against.
        inngest_send: callable that sends an Inngest event (e.g. ``inngest_client.send_sync``).
        session_factory: callable returning a ``Session`` (e.g. ``get_session``).
        tokenizer: HuggingFace tokenizer with ``.encode(text) -> list[int]``.
        reward_strategy: per-agent credit assignment.  Defaults to ``IndependentTaskReward``.
        timeout_s: max seconds to wait for all episodes to complete.
        poll_interval_s: sleep between DB polls.

    Returns:
        A ``rollout_func(prompts, trainer) -> dict`` suitable for ``GRPOTrainer``.
    """
    if reward_strategy is None:
        reward_strategy = IndependentTaskReward()

    def rollout_func(
        prompts: list[PromptInput],
        trainer: object,
    ) -> dict[str, object]:
        run_ids: list[UUID] = []

        # Tokenize TRL's chat-format prompts into prompt_ids for the return value.
        prompt_ids_per_prompt: list[list[int]] = []
        for prompt in prompts:
            if isinstance(prompt, list) and prompt and isinstance(prompt[0], dict):
                text = tokenizer.apply_chat_template(
                    prompt,  # type: ignore[arg-type]
                    tokenize=False,
                    add_generation_prompt=True,
                )
                prompt_ids_per_prompt.append(tokenizer.encode(text))
            elif isinstance(prompt, str):
                prompt_ids_per_prompt.append(tokenizer.encode(prompt))
            else:
                prompt_ids_per_prompt.append([])

        # 1. Create runs and fire Inngest events
        for _prompt in prompts:
            run_id = new_id()

            with session_factory() as session:
                run = RunRecord(
                    id=run_id,
                    experiment_definition_id=definition_id,
                    status=RunStatus.PENDING,
                )
                session.add(run)
                session.commit()

            inngest_send(
                inngest_lib.Event(
                    name=WorkflowStartedEvent.name,
                    data=WorkflowStartedEvent(
                        run_id=run_id,
                        definition_id=definition_id,
                    ).model_dump(mode="json"),
                )
            )
            run_ids.append(run_id)

        logger.info("Fired %d episodes via Inngest, polling for completion...", len(run_ids))

        # 2. Wait for all episodes to complete
        poll_until_all_complete(
            session_factory,
            run_ids,
            timeout_s=timeout_s,
            poll_interval_s=poll_interval_s,
        )

        # 3. Batch-load generation turns + evaluation scores (2 queries, not 2*N)
        all_prompt_ids: list[list[int]] = []
        all_completion_ids: list[list[int]] = []
        all_logprobs: list[list[float]] = []
        all_rewards: list[float] = []
        all_env_masks: list[list[int]] = []

        with session_factory() as session:
            all_turns = list(
                session.exec(
                    select(RunGenerationTurn)
                    .where(RunGenerationTurn.run_id.in_(run_ids))  # type: ignore[union-attr]
                    .order_by(
                        RunGenerationTurn.run_id,
                        RunGenerationTurn.task_execution_id,
                        RunGenerationTurn.turn_index,
                    )
                ).all()
            )
            all_evals = list(
                session.exec(
                    select(RunTaskEvaluation).where(RunTaskEvaluation.run_id.in_(run_ids))  # type: ignore[union-attr]
                ).all()
            )

        # Group by run_id in Python
        turns_by_run: dict[UUID, list[RunGenerationTurn]] = defaultdict(list)
        for turn in all_turns:
            turns_by_run[turn.run_id].append(turn)

        evals_by_run: dict[UUID, dict[str, float]] = defaultdict(dict)
        for ev in all_evals:
            if ev.score is not None:
                evals_by_run[ev.run_id][str(ev.definition_task_id)] = ev.score

        # Build a mapping from task_execution_id -> definition_task_id so the
        # reward strategy can look up eval scores by execution ID.
        exec_to_def_task: dict[str, str] = {}
        with session_factory() as session:
            execs = list(
                session.exec(
                    select(RunTaskExecution).where(RunTaskExecution.run_id.in_(run_ids))  # type: ignore[union-attr]
                ).all()
            )
            for ex in execs:
                exec_to_def_task[str(ex.id)] = str(ex.definition_task_id)

        # Remap eval scores so they're keyed by task_execution_id
        # (what the generation turns and reward strategy use).
        evals_by_run_remapped: dict[UUID, dict[str, float]] = defaultdict(dict)
        for run_id_key, scores in evals_by_run.items():
            for def_task_id, score in scores.items():
                for exec_id, mapped_def_id in exec_to_def_task.items():
                    if mapped_def_id == def_task_id:
                        evals_by_run_remapped[run_id_key][exec_id] = score

        for i, run_id in enumerate(run_ids):
            prompt_ids = prompt_ids_per_prompt[i] if i < len(prompt_ids_per_prompt) else []

            trajectories = extract_agent_trajectories(
                turns_by_run.get(run_id, []),
                evals_by_run_remapped.get(run_id, {}),
                tokenizer,
                prompt_text="",
                reward_strategy=reward_strategy,
            )

            for traj in trajectories:
                all_prompt_ids.append(prompt_ids)
                all_completion_ids.append(traj.completion_ids)
                all_logprobs.append(traj.logprobs)
                all_rewards.append(traj.reward)
                all_env_masks.append(traj.env_mask)

        logger.info(
            "Extracted %d trajectories from %d episodes",
            len(all_rewards),
            len(run_ids),
        )

        return {
            "prompt_ids": all_prompt_ids,
            "completion_ids": all_completion_ids,
            "logprobs": all_logprobs,
            "completion_reward": all_rewards,
            "env_mask": all_env_masks,
        }

    return rollout_func
