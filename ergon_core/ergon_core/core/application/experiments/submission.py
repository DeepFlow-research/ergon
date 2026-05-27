"""Experiment submit orchestration for selected sample materialization."""

from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from pydantic import JsonValue
from sqlmodel import Session

from ergon_core.api.experiment.experiment import Experiment, ExperimentSubmitResult
from ergon_core.api.experiment.sample import Sample
from ergon_core.api.experiment.sampling import Sampler, SamplingContext
from ergon_core.core.application.events.runtime import WorkflowStartedEvent
from ergon_core.core.application.experiments.candidate_pool import (
    SampleCandidatePool,
    sample_from_pool_entry,
)
from ergon_core.core.application.experiments.persistence import CoreExperimentPersistencePort
from ergon_core.core.application.experiments.repository import (
    record_sampler_invocation,
)
from ergon_core.core.application.samples.materialization import materialize_sample
from ergon_core.core.infrastructure.inngest.client import InngestEvent, inngest_client
from ergon_core.core.persistence.experiments.models import (
    ExperimentSamplePoolEntryRow,
    ExperimentSamplerInvocationRow,
)
from ergon_core.core.persistence.shared.enums import SampleStatus
from ergon_core.core.persistence.telemetry.models import SampleRecord


class EventBus(Protocol):
    async def publish(self, event: WorkflowStartedEvent) -> None: ...


class InngestWorkflowEventBus:
    async def publish(self, event: WorkflowStartedEvent) -> None:
        await inngest_client.send(
            InngestEvent(
                name=WorkflowStartedEvent.name,
                data=event.model_dump(mode="json"),
            )
        )


class ExperimentSubmissionService:
    def __init__(self, *, session: Session, event_bus: EventBus | None = None) -> None:
        self._session = session
        self._event_bus = event_bus or InngestWorkflowEventBus()

    @classmethod
    def for_session(
        cls,
        session: Session,
        *,
        event_bus: EventBus | None = None,
    ) -> "ExperimentSubmissionService":
        return cls(session=session, event_bus=event_bus)

    async def submit(
        self,
        *,
        experiment: Experiment,
        k: int,
        sampler: Sampler,
        candidate_pool_size: int | None,
        policy_version: int | None = None,
    ) -> ExperimentSubmitResult:
        handle = await CoreExperimentPersistencePort(self._session).persist_experiment(experiment)
        pool_size = candidate_pool_size or k
        pool = SampleCandidatePool(self._session)
        entries = pool.fill(
            experiment=experiment,
            handle=handle,
            candidate_pool_size=pool_size,
        )
        candidates = [await sample_from_pool_entry(entry) for entry in entries]
        sampler_selected = list(
            await sampler.select(
                samples=candidates,
                k=k,
                context=SamplingContext(
                    experiment_id=handle.experiment_id,
                    candidate_pool_size=pool_size,
                ),
            )
        )
        selected = sampler_selected[:k]
        selected_entries = _entries_for_selected_samples(entries=entries, selected=selected)
        invocation = record_sampler_invocation(
            session=self._session,
            experiment_ref=handle,
            sampler_name=sampler.name,
            requested_k=k,
            candidate_pool_size=pool_size,
            selected_count=len(selected_entries),
            policy_version=policy_version,
            sampler_config=sampler.config(),
        )
        pool.mark_selected(selected_entries, sampler_invocation_id=invocation.id)
        sample_ids = self._materialize_selected(
            invocation=invocation,
            selected=selected,
            selected_entries=selected_entries,
        )
        self._session.commit()
        await self._start_samples(sample_ids)
        return ExperimentSubmitResult(
            experiment_id=handle.experiment_id,
            sampler_invocation_id=invocation.id,
            requested_k=k,
            candidate_pool_size=pool_size,
            selected_count=len(sample_ids),
            sample_ids=sample_ids,
        )

    def _materialize_selected(
        self,
        *,
        invocation: ExperimentSamplerInvocationRow,
        selected: Sequence[Sample],
        selected_entries: Sequence[ExperimentSamplePoolEntryRow],
    ) -> list[UUID]:
        sample_ids: list[UUID] = []
        for sample, entry in zip(selected, selected_entries, strict=True):
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
                assignment_json=_assignment_json(sample),
                experiment=str(entry.experiment_id),
                status=SampleStatus.PENDING,
            )
            self._session.add(row)
            self._session.flush()
            materialize_sample(session=self._session, sample=sample, sample_row=row)
            sample_ids.append(row.id)
        self._session.flush()
        return sample_ids

    async def _start_samples(self, sample_ids: Sequence[UUID]) -> None:
        for sample_id in sample_ids:
            await self._event_bus.publish(WorkflowStartedEvent(sample_id=sample_id))


def _entries_for_selected_samples(
    *,
    entries: Sequence[ExperimentSamplePoolEntryRow],
    selected: Sequence[Sample],
) -> list[ExperimentSamplePoolEntryRow]:
    remaining = list(entries)
    selected_entries: list[ExperimentSamplePoolEntryRow] = []
    for sample in selected:
        for index, entry in enumerate(remaining):
            if (
                entry.sample_key == sample.sample_key
                and entry.sample_json.get("environment_name") == sample.environment_name
            ):
                selected_entries.append(remaining.pop(index))
                break
        else:
            raise ValueError(
                "Sampler returned a sample that was not present in the candidate pool: "
                f"{sample.environment_name}/{sample.sample_key}"
            )
    return selected_entries


def _assignment_json(sample: Sample) -> dict[str, JsonValue]:
    return {
        "sample_key": sample.sample_key,
        "sample_name": sample.name,
        "environment_name": sample.environment_name,
        "sample_ref": dict(sample.sample_ref),
        "source_metadata": dict(sample.source_metadata),
        "metadata": dict(sample.metadata),
    }
