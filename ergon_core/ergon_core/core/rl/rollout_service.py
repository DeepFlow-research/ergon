"""Rollout-as-a-Service: orchestrate episode batches for RL trainers.

Encapsulates all logic previously inline in trl_adapter.py. Both the
HTTP endpoints (/rollouts/) and any in-process callers delegate here.

Batch state is durable in PG — survives API restarts.
"""

import logging
from collections import defaultdict
from collections.abc import Callable, Sequence
from uuid import UUID

import inngest
from ergon_core.core.application.experiments.candidate_pool import (
    reserve_sample_pool_entries_for_sampler,
    sample_from_pool_entry,
)
from ergon_core.core.application.samples.materialization import materialize_sample
from ergon_core.core.persistence.context.models import SampleContextEvent
from ergon_core.core.persistence.experiments.models import (
    ExperimentSamplerInvocationRow,
    ExperimentSamplePoolEntryRow,
)
from ergon_core.core.persistence.shared.enums import (
    TERMINAL_SAMPLE_STATUSES,
    SampleStatus,
)
from ergon_core.core.persistence.telemetry.models import (
    RolloutBatch,
    RolloutBatchSampleMembership,
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
    RolloutBatchSummary,
    Trajectory,
    TrainingRolloutRequest,
)
from ergon_core.core.application.events.runtime import SampleStartedEvent
from sqlmodel import Session, select

logger = logging.getLogger(__name__)


class RolloutService:
    """Orchestrate rollout batches: create runs, fire events, poll, extract.

    Lifecycle:
      1. Trainer calls ``submit_experiment_batch()`` → SampleRecords + RolloutBatch created, Inngest events fired
      2. Trainer polls ``poll()`` → returns RUNNING until all episodes finish
      3. When all terminal → ``poll()`` extracts trajectories and returns COMPLETE

    Batch state is durable in PG via RolloutBatch/RolloutBatchSampleMembership tables.
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

    def create_rollout_batch(
        self,
        session: Session,
        *,
        sample_ids: Sequence[UUID],
        experiment_id: UUID | None = None,
        sampler_invocation_id: UUID | None = None,
    ) -> RolloutBatchSummary:
        """Create a durable sample-based batch without launching samples."""
        batch = RolloutBatch(
            experiment_id=experiment_id,
            sampler_invocation_id=sampler_invocation_id,
            status=BatchStatus.PENDING,
        )
        session.add(batch)
        session.flush()
        for ordinal, sample_id in enumerate(sample_ids):
            session.add(
                RolloutBatchSampleMembership(
                    batch_id=batch.id,
                    sample_id=sample_id,
                    ordinal=ordinal,
                )
            )
        session.flush()
        return RolloutBatchSummary(
            batch_id=batch.id,
            sample_ids=list(sample_ids),
            status=BatchStatus(batch.status),
            experiment_id=batch.experiment_id,
            sampler_invocation_id=batch.sampler_invocation_id,
        )

    def get_rollout_batch(self, session: Session, batch_id: UUID) -> RolloutBatchSummary | None:
        """Load durable batch membership by sample id."""
        batch = session.get(RolloutBatch, batch_id)
        if batch is None:
            return None
        sample_ids = self._batch_sample_ids(session, batch_id)
        return RolloutBatchSummary(
            batch_id=batch.id,
            sample_ids=sample_ids,
            status=BatchStatus(batch.status),
            experiment_id=batch.experiment_id,
            sampler_invocation_id=batch.sampler_invocation_id,
        )

    def get_rollout_batch_by_id(self, batch_id: UUID) -> RolloutBatchSummary | None:
        """Load durable batch membership using the service session factory."""
        with self._session_factory() as session:
            return self.get_rollout_batch(session, batch_id)

    async def submit_experiment_batch(
        self,
        request: TrainingRolloutRequest,
    ) -> RolloutBatchSummary:
        """Launch a trainer batch from already-buffered experiment candidates."""
        with self._session_factory() as session:
            invocation, selected_entries = reserve_sample_pool_entries_for_sampler(
                session=session,
                experiment_id=request.experiment_id,
                k=request.k,
                candidate_pool_size=request.candidate_pool_size,
                sampler_name=request.sampler,
                sampler_config=request.sampler_config,
            )
            sample_ids = await self._materialize_pool_entries(
                session=session,
                invocation=invocation,
                entries=selected_entries,
            )
            summary = self.create_rollout_batch(
                session,
                sample_ids=sample_ids,
                experiment_id=request.experiment_id,
                sampler_invocation_id=invocation.id,
            )
            session.commit()

        for sample_id in summary.sample_ids:
            self._inngest_send(
                inngest.Event(
                    name=SampleStartedEvent.name,
                    data=SampleStartedEvent(sample_id=sample_id).model_dump(mode="json"),
                )
            )
        return summary

    async def _materialize_pool_entries(
        self,
        *,
        session: Session,
        invocation: ExperimentSamplerInvocationRow,
        entries: Sequence[ExperimentSamplePoolEntryRow],
    ) -> list[UUID]:
        sample_ids: list[UUID] = []
        for entry in entries:
            sample = await sample_from_pool_entry(entry)
            row = SampleRecord(
                experiment_id=entry.experiment_id,
                environment_id=entry.environment_id,
                sampler_invocation_id=invocation.id,
                pool_entry_id=entry.id,
                sample_key=sample.sample_key,
                sample_ref_json=dict(sample.sample_ref),
                benchmark_type="experiment",
                instance_key=sample.sample_key,
                sample_id=sample.sample_key,
                worker_team_json={},
                dependency_extras_json={},
                assignment_json={
                    "sample_key": sample.sample_key,
                    "sample_name": sample.name,
                    "environment_name": sample.environment_name,
                    "sample_ref": dict(sample.sample_ref),
                    "source_metadata": dict(sample.source_metadata),
                    "metadata": dict(sample.metadata),
                },
                experiment=str(entry.experiment_id),
                status=SampleStatus.PENDING,
            )
            session.add(row)
            session.flush()
            materialize_sample(session=session, sample=sample, sample_row=row)
            sample_ids.append(row.id)
        session.flush()
        return sample_ids

    def poll(self, batch_id: UUID) -> PollResponse | None:
        """Non-blocking status check. Extracts trajectories when all done."""
        with self._session_factory() as session:
            batch = session.get(RolloutBatch, batch_id)
            if batch is None:
                return None

            sample_ids = self._batch_sample_ids(session, batch_id)

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

            sample_ids = self._batch_sample_ids(session, batch_id)

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

    def _batch_sample_ids(self, session: Session, batch_id: UUID) -> list[UUID]:
        memberships = list(
            session.exec(
                select(RolloutBatchSampleMembership)
                .where(RolloutBatchSampleMembership.batch_id == batch_id)
                .order_by(
                    RolloutBatchSampleMembership.ordinal,
                    RolloutBatchSampleMembership.sample_id,
                )
            ).all()
        )
        return [membership.sample_id for membership in memberships]

    def _extract_trajectories(self, sample_ids: list[UUID]) -> list[Trajectory]:
        """Load context events + evals from DB, run extraction, build Trajectory list."""
        with self._session_factory() as session:
            all_events = list(
                session.exec(
                    select(SampleContextEvent)
                    .where(SampleContextEvent.sample_id.in_(sample_ids))  # type: ignore[union-attr]
                    .order_by(
                        SampleContextEvent.sample_id,
                        SampleContextEvent.task_attempt_id,
                        SampleContextEvent.sequence,
                    )
                ).all()
            )
            all_evals = list(
                session.exec(
                    select(SampleTaskEvaluation).where(
                        SampleTaskEvaluation.sample_id.in_(sample_ids)
                    )  # type: ignore[union-attr]
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
