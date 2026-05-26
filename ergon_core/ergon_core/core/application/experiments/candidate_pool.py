"""Candidate-pool persistence for public experiment samples."""

from collections.abc import Sequence
from uuid import UUID, uuid4

from sqlmodel import Session, select

from ergon_core.api.experiment.experiment import Experiment, ExperimentRef
from ergon_core.api.experiment.sample import Sample
from ergon_core.api.benchmark import Task
from ergon_core.core.persistence.experiments.models import (
    ExperimentEnvironmentRow,
    ExperimentSamplePoolEntryRow,
)
from ergon_core.core.shared.utils import utcnow


class SampleCandidatePool:
    def __init__(
        self,
        session: Session,
        *,
        max_duplicate_pulls_per_environment: int = 1_000,
    ) -> None:
        self._session = session
        self._max_duplicate_pulls_per_environment = max_duplicate_pulls_per_environment

    def fill(
        self,
        *,
        experiment: Experiment,
        handle: ExperimentRef,
        candidate_pool_size: int,
    ) -> list[ExperimentSamplePoolEntryRow]:
        entries = self._pending_unselected_entries(handle.experiment_id)
        if len(entries) >= candidate_pool_size:
            return entries[:candidate_pool_size]

        env_rows = {
            environment.name: self._environment_row(handle.experiment_id, environment.name)
            for environment in experiment.environments
        }
        known_keys = self._known_keys_by_environment(handle.experiment_id)
        iterators = {
            environment.name: iter(environment.iter_samples())
            for environment in experiment.environments
        }
        active_names = [environment.name for environment in experiment.environments]
        duplicate_pulls = dict.fromkeys(active_names, 0)

        while active_names and len(entries) < candidate_pool_size:
            for environment_name in list(active_names):
                try:
                    sample = next(iterators[environment_name])
                except StopIteration:
                    active_names.remove(environment_name)
                    continue

                if sample.sample_key in known_keys.setdefault(environment_name, set()):
                    duplicate_pulls[environment_name] += 1
                    if (
                        duplicate_pulls[environment_name]
                        >= self._max_duplicate_pulls_per_environment
                    ):
                        active_names.remove(environment_name)
                    continue

                duplicate_pulls[environment_name] = 0
                env_row = env_rows[environment_name]
                entries.append(
                    self._record_candidate(
                        handle=handle,
                        environment_id=env_row.id,
                        sample=sample,
                    )
                )
                known_keys[environment_name].add(sample.sample_key)
                if len(entries) >= candidate_pool_size:
                    break
        return entries

    def mark_selected(
        self,
        entries: Sequence[ExperimentSamplePoolEntryRow],
        *,
        sampler_invocation_id: UUID,
    ) -> None:
        selected_at = utcnow()
        for entry in entries:
            entry.selected = True
            entry.selected_at = selected_at
            entry.sampler_invocation_id = sampler_invocation_id
            self._session.add(entry)
        self._session.flush()

    def _pending_unselected_entries(
        self,
        experiment_id: UUID,
    ) -> list[ExperimentSamplePoolEntryRow]:
        return self._session.exec(
            select(ExperimentSamplePoolEntryRow)
            .where(ExperimentSamplePoolEntryRow.experiment_id == experiment_id)
            .where(ExperimentSamplePoolEntryRow.selected.is_(False))
            .where(ExperimentSamplePoolEntryRow.discarded.is_(False))
            .order_by(ExperimentSamplePoolEntryRow.created_at, ExperimentSamplePoolEntryRow.id)
        ).all()

    def _environment_row(
        self,
        experiment_id: UUID,
        environment_name: str,
    ) -> ExperimentEnvironmentRow:
        return self._session.exec(
            select(ExperimentEnvironmentRow)
            .where(ExperimentEnvironmentRow.experiment_id == experiment_id)
            .where(ExperimentEnvironmentRow.name == environment_name)
        ).one()

    def _known_keys_by_environment(self, experiment_id: UUID) -> dict[str, set[str]]:
        rows = self._session.exec(
            select(ExperimentSamplePoolEntryRow, ExperimentEnvironmentRow.name)
            .join(
                ExperimentEnvironmentRow,
                ExperimentSamplePoolEntryRow.environment_id == ExperimentEnvironmentRow.id,
            )
            .where(ExperimentSamplePoolEntryRow.experiment_id == experiment_id)
        ).all()
        known: dict[str, set[str]] = {}
        for entry, environment_name in rows:
            known.setdefault(environment_name, set()).add(entry.sample_key)
        return known

    def _record_candidate(
        self,
        *,
        handle: ExperimentRef,
        environment_id: UUID,
        sample: Sample,
    ) -> ExperimentSamplePoolEntryRow:
        row = ExperimentSamplePoolEntryRow(
            experiment_id=handle.experiment_id,
            environment_id=environment_id,
            sample_key=sample.sample_key,
            sample_json=sample.model_dump(mode="json"),
        )
        self._session.add(row)
        self._session.flush()
        return row


async def sample_from_pool_entry(entry: ExperimentSamplePoolEntryRow) -> Sample:
    """Rehydrate retained candidate JSON into an authored, unmaterialized Sample."""

    payload = dict(entry.sample_json)
    task_snapshots = payload.pop("tasks", [])
    tasks = [await _task_from_candidate_snapshot(task_json) for task_json in task_snapshots]
    return Sample.from_tasks(
        name=str(payload["name"]),
        sample_key=str(payload["sample_key"]),
        environment_name=str(payload["environment_name"]),
        tasks=tasks,
        sample_ref=payload.get("sample_ref") if isinstance(payload.get("sample_ref"), dict) else None,
        source_metadata=(
            payload.get("source_metadata")
            if isinstance(payload.get("source_metadata"), dict)
            else None
        ),
        metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else None,
    )


async def _task_from_candidate_snapshot(task_json: object) -> Task:
    if not isinstance(task_json, dict):
        raise ValueError(f"Candidate task snapshot must be an object, got {type(task_json).__name__}")
    task = await Task.from_definition(task_json, task_id=uuid4())
    # Candidate-pool rows are not runtime materializations. We use the existing
    # `_type` dispatch path to rebuild object-bound config, then clear the
    # temporary id so materialization remains the only runtime-id boundary.
    task._task_id = None
    return task
