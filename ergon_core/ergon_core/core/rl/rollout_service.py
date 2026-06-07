"""Rollout-as-a-Service: orchestrate episode batches for RL trainers.

Encapsulates all logic previously inline in trl_adapter.py. Both the
HTTP endpoints (/rollouts/) and any in-process callers delegate here.

Batch state is durable in PG — survives API restarts.
"""

import logging
from collections.abc import Callable, Sequence
from uuid import UUID

import inngest
from ergon_core.core.application.experiments.candidate_pool import (
    reserve_sample_pool_entries_for_sampler,
    sample_from_pool_entry,
)
from ergon_core.core.application.samples.materialization import materialize_sample
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
)
from ergon_core.core.views.rl import RlEpisodeReadService, RlProjectionService
from ergon_core.core.views.rl.models import RlProjectedStep
from ergon_core.core.rl.rollout_types import (
    TrainerActorIdentity,
    TrainerTrainingRecord,
)
from ergon_core.core.rl.rewards import IndependentTaskReward, RewardStrategy
from ergon_core.core.rl.rollout_types import (
    BatchStatus,
    EpisodeFailure,
    PollResponse,
    RolloutBatchSummary,
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
      3. When all terminal → ``poll()`` projects training records and returns COMPLETE

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
        self._reward_strategy = reward_strategy or IndependentTaskReward()

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
        """Non-blocking status check. Projects training records when all done."""
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

        training_records = self._build_training_records(completed_ids)
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
            "Batch %s complete: %d training records, %d failures",
            batch_id,
            len(training_records),
            len(failures),
        )
        return PollResponse(
            batch_id=batch_id,
            status=BatchStatus.COMPLETE,
            completed=len(completed_ids),
            total=len(sample_ids),
            training_records=training_records,
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

    def _build_training_records(self, sample_ids: list[UUID]) -> list[TrainerTrainingRecord]:
        """Project completed samples into the first TRL example response shape."""
        result: list[TrainerTrainingRecord] = []
        with self._session_factory() as session:
            episode_reader = RlEpisodeReadService(session)
            projector = RlProjectionService()
            for sample_id in sample_ids:
                episode = episode_reader.get_episode(sample_id)
                reward = episode.normalized_reward
                if reward is None:
                    reward = 0.0
                for span in projector.iter_actor_spans(episode, group_by="actor_slug"):
                    if not span.records:
                        continue
                    prompt_ids = _token_ids_for_kind(span.records, "observation")
                    completion_ids = _token_ids_for_kind(span.records, "action")
                    logprobs = _logprobs_for_kind(span.records, "action")
                    if not prompt_ids and not completion_ids:
                        continue
                    first = span.records[0]
                    result.append(
                        TrainerTrainingRecord(
                            sample_id=sample_id,
                            actor=TrainerActorIdentity(
                                actor_slug=first.actor.actor_slug,
                                base_worker_slug=first.actor.base_worker_slug,
                                parent_actor_slug=first.actor.parent_actor_slug,
                                task_id=first.actor.task_id,
                                parent_task_id=first.actor.parent_task_id,
                            ),
                            prompt_ids=prompt_ids,
                            completion_ids=completion_ids,
                            logprobs=logprobs,
                            reward=reward,
                            task_id=first.task_id,
                            task_attempt_id=first.task_attempt_id,
                        )
                    )
        return result


def _token_ids_for_kind(records: list[RlProjectedStep], step_kind: str) -> list[int]:
    token_ids: list[int] = []
    for record in records:
        if record.step_kind != step_kind or record.token_metadata is None:
            continue
        token_ids.extend(record.token_metadata.token_ids or [])
    return token_ids


def _logprobs_for_kind(records: list[RlProjectedStep], step_kind: str) -> list[float]:
    logprobs: list[float] = []
    for record in records:
        if (
            record.step_kind != step_kind
            or record.token_metadata is None
            or record.token_metadata.logprobs is None
        ):
            continue
        logprobs.extend(item.logprob for item in record.token_metadata.logprobs)
    return logprobs
