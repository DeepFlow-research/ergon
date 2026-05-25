"""Rollout-as-a-Service: orchestrate episode batches for RL trainers.

Encapsulates all logic previously inline in trl_adapter.py. Both the
HTTP endpoint (/rollouts/) and any in-process callers delegate here.

Batch state is durable in PG — survives API restarts.
"""

import logging
from collections import defaultdict
from collections.abc import Callable
from uuid import UUID, uuid4

import inngest
from ergon_core.core.persistence.context.models import SampleContextEvent
from ergon_core.core.persistence.definitions.models import ExperimentDefinition
from ergon_core.core.persistence.shared.enums import (
    TERMINAL_SAMPLE_STATUSES,
    SampleStatus,
)
from ergon_core.core.persistence.shared.ids import new_id
from ergon_core.core.persistence.telemetry.models import (
    RolloutBatch,
    RolloutBatchRun,
    SampleRecord,
    SampleTaskEvaluation,
    SampleTaskAttempt,
)
from ergon_core.core.rl.extraction import (
    Tokenizer,
    extract_agent_trajectories,
)
from ergon_core.core.rl.rewards import IndependentTaskReward, RewardStrategy
from ergon_core.core.rl.rollout_types import (
    BatchStatus,
    EpisodeFailure,
    PollResponse,
    SubmitRequest,
    SubmitResponse,
    Trajectory,
)
from ergon_core.core.application.events.runtime import WorkflowStartedEvent
from sqlmodel import Session, select

logger = logging.getLogger(__name__)


class RolloutService:
    """Orchestrate rollout batches: create runs, fire events, poll, extract.

    Lifecycle:
      1. Trainer calls ``submit()`` → SampleRecords + RolloutBatch created, Inngest events fired
      2. Trainer polls ``poll()`` → returns RUNNING until all episodes finish
      3. When all terminal → ``poll()`` extracts trajectories and returns COMPLETE

    Batch state is durable in PG via RolloutBatch/RolloutBatchRun tables.
    API restarts do not lose batch mappings.
    """

    def __init__(
        self,
        session_factory: Callable[[], Session],
        inngest_send: Callable[[inngest.Event], None],
        tokenizer_name: str,
        reward_strategy: RewardStrategy | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._inngest_send = inngest_send
        self._tokenizer_name = tokenizer_name
        self._tokenizer: Tokenizer | None = None
        self._reward_strategy = reward_strategy or IndependentTaskReward()

    def _get_tokenizer(self) -> Tokenizer:
        if self._tokenizer is None:
            from transformers import AutoTokenizer

            logger.info("Loading tokenizer: %s", self._tokenizer_name)
            self._tokenizer = AutoTokenizer.from_pretrained(self._tokenizer_name)
        return self._tokenizer

    def submit(self, request: SubmitRequest) -> SubmitResponse:
        """Create SampleRecords, RolloutBatch, and fire Inngest workflow/started events."""
        batch_id = uuid4()
        sample_ids: list[UUID] = []

        with self._session_factory() as session:
            definition = session.get(ExperimentDefinition, request.definition_id)
            benchmark_type = definition.benchmark_type if definition else "rl-rollout"
            session.add(
                RolloutBatch(
                    id=batch_id,
                    definition_id=request.definition_id,
                    status=BatchStatus.PENDING,
                )
            )

            for index in range(request.num_episodes):
                sample_id = new_id()
                session.add(
                    SampleRecord(
                        id=sample_id,
                        definition_id=request.definition_id,
                        benchmark_type=benchmark_type,
                        instance_key=f"episode-{index}",
                        worker_team_json={"primary": "rl-rollout"},
                        model_target=request.model_target_override,
                        status=SampleStatus.PENDING,
                    )
                )
                session.add(
                    RolloutBatchRun(
                        id=new_id(),
                        batch_id=batch_id,
                        sample_id=sample_id,
                    )
                )
                sample_ids.append(sample_id)

            session.commit()

        for sample_id in sample_ids:
            self._inngest_send(
                inngest.Event(
                    name=WorkflowStartedEvent.name,
                    data=WorkflowStartedEvent(
                        sample_id=sample_id,
                        definition_id=request.definition_id,
                    ).model_dump(mode="json"),
                )
            )

        logger.info(
            "Submitted batch %s: %d episodes for definition %s",
            batch_id,
            request.num_episodes,
            request.definition_id,
        )
        return SubmitResponse(
            batch_id=batch_id,
            sample_ids=sample_ids,
            status=BatchStatus.PENDING,
        )

    def poll(self, batch_id: UUID) -> PollResponse | None:
        """Non-blocking status check. Extracts trajectories when all done."""
        with self._session_factory() as session:
            batch = session.get(RolloutBatch, batch_id)
            if batch is None:
                return None

            batch_runs = list(
                session.exec(
                    select(RolloutBatchRun).where(RolloutBatchRun.batch_id == batch_id)
                ).all()
            )
            sample_ids = [br.sample_id for br in batch_runs]

            if not sample_ids:
                return PollResponse(
                    batch_id=batch_id,
                    status=BatchStatus.COMPLETE,
                )

            runs = list(
                session.exec(
                    select(SampleRecord).where(
                        SampleRecord.id.in_(sample_ids)  # type: ignore[union-attr]
                    )
                ).all()
            )

        terminal = set(TERMINAL_SAMPLE_STATUSES)
        completed_ids: list[UUID] = []
        failed_ids: list[UUID] = []

        for run in runs:
            if run.status not in terminal:
                continue
            if run.status == SampleStatus.COMPLETED:
                completed_ids.append(run.id)
            else:
                failed_ids.append(run.id)

        total_terminal = len(completed_ids) + len(failed_ids)
        if total_terminal < len(sample_ids):
            return PollResponse(
                batch_id=batch_id,
                status=BatchStatus.RUNNING,
                completed=len(completed_ids),
                total=len(sample_ids),
            )

        trajectories = self._extract_trajectories(completed_ids)
        failures = [
            EpisodeFailure(sample_id=rid, error="episode failed or timed out") for rid in failed_ids
        ]

        with self._session_factory() as session:
            batch = session.get(RolloutBatch, batch_id)
            if batch is not None:
                batch.status = BatchStatus.COMPLETE
                session.add(batch)
                session.commit()

        logger.info(
            "Batch %s complete: %d trajectories, %d failures",
            batch_id,
            len(trajectories),
            len(failures),
        )
        return PollResponse(
            batch_id=batch_id,
            status=BatchStatus.COMPLETE,
            completed=len(completed_ids),
            total=len(sample_ids),
            trajectories=trajectories,
            failures=failures,
        )

    def cancel(self, batch_id: UUID) -> None:
        """Mark all non-terminal runs in the batch as cancelled."""
        with self._session_factory() as session:
            batch = session.get(RolloutBatch, batch_id)
            if batch is None:
                return

            batch_runs = list(
                session.exec(
                    select(RolloutBatchRun).where(RolloutBatchRun.batch_id == batch_id)
                ).all()
            )
            sample_ids = [br.sample_id for br in batch_runs]

            if sample_ids:
                runs = list(
                    session.exec(
                        select(SampleRecord).where(
                            SampleRecord.id.in_(sample_ids)  # type: ignore[union-attr]
                        )
                    ).all()
                )
                for run in runs:
                    if run.status not in set(TERMINAL_SAMPLE_STATUSES):
                        run.status = SampleStatus.CANCELLED
                        session.add(run)

            batch.status = BatchStatus.CANCELLED
            session.add(batch)
            session.commit()

    def _extract_trajectories(self, sample_ids: list[UUID]) -> list[Trajectory]:
        """Load context events + evals from DB, run extraction, build Trajectory list."""
        with self._session_factory() as session:
            all_events = list(
                session.exec(
                    select(SampleContextEvent)
                    .where(SampleContextEvent.sample_id.in_(sample_ids))  # type: ignore[union-attr]
                    .order_by(
                        SampleContextEvent.sample_id,
                        SampleContextEvent.task_execution_id,
                        SampleContextEvent.sequence,
                    )
                ).all()
            )
            all_evals = list(
                session.exec(
                    select(SampleTaskEvaluation).where(SampleTaskEvaluation.sample_id.in_(sample_ids))  # type: ignore[union-attr]
                ).all()
            )
            all_execs = list(
                session.exec(
                    select(SampleTaskAttempt).where(SampleTaskAttempt.sample_id.in_(sample_ids))  # type: ignore[union-attr]
                ).all()
            )

        events_by_run: dict[UUID, list[SampleContextEvent]] = defaultdict(list)
        for event in all_events:
            events_by_run[event.sample_id].append(event)

        evals_by_run: dict[UUID, dict[str, float]] = defaultdict(dict)
        for ev in all_evals:
            if ev.score is not None:
                evals_by_run[ev.sample_id][str(ev.task_id)] = ev.score

        exec_to_def_task: dict[str, str] = {}
        for ex in all_execs:
            exec_to_def_task[str(ex.id)] = str(ex.task_id)

        evals_remapped: dict[UUID, dict[str, float]] = defaultdict(dict)
        for sample_id, scores in evals_by_run.items():
            for def_task_id, score in scores.items():
                for exec_id, mapped_def_id in exec_to_def_task.items():
                    if mapped_def_id == def_task_id:
                        evals_remapped[sample_id][exec_id] = score

        result: list[Trajectory] = []
        tokenizer = self._get_tokenizer()
        for sample_id in sample_ids:
            run_events = events_by_run.get(sample_id, [])
            agent_trajs = extract_agent_trajectories(
                run_events,
                evals_remapped.get(sample_id, {}),
                tokenizer,
                reward_strategy=self._reward_strategy,
            )
            for traj in agent_trajs:
                result.append(
                    Trajectory(
                        sample_id=sample_id,
                        agent_id=traj.agent_id,
                        prompt_ids=traj.prompt_ids,
                        completion_ids=traj.completion_ids,
                        logprobs=traj.logprobs,
                        env_mask=traj.env_mask,
                        reward=traj.reward,
                        num_turns=traj.turns,
                    )
                )
        return result
