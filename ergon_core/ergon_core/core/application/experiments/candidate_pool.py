"""Candidate-pool persistence for public experiment samples."""

from collections.abc import Sequence
from uuid import UUID, uuid4

from pydantic import JsonValue
from sqlmodel import Session

from ergon_core.api.benchmark import Task
from ergon_core.api.benchmark.task import EmptyTaskPayload
from ergon_core.api.experiment.experiment import Experiment, ExperimentRef
from ergon_core.api.experiment.sample import Sample
from ergon_core.core.application.experiments.repository import (
    ExperimentRepository,
    record_sampler_invocation,
)
from ergon_core.core.persistence.experiments.models import (
    ExperimentRow,
    ExperimentSamplerInvocationRow,
    ExperimentSamplePoolEntryRow,
)


class SampleCandidatePool:
    def __init__(
        self,
        session: Session,
        *,
        max_duplicate_pulls_per_environment: int = 1_000,
        repository: ExperimentRepository | None = None,
    ) -> None:
        self._repository = repository or ExperimentRepository(session)
        self._max_duplicate_pulls_per_environment = max_duplicate_pulls_per_environment

    def fill(
        self,
        *,
        experiment: Experiment,
        handle: ExperimentRef,
        candidate_pool_size: int,
    ) -> list[ExperimentSamplePoolEntryRow]:
        entries = self._repository.pending_unselected_pool_entries(handle.experiment_id)
        if len(entries) >= candidate_pool_size:
            return entries[:candidate_pool_size]

        env_rows = {
            environment.name: self._repository.experiment_environment_row(
                experiment_id=handle.experiment_id,
                environment_name=environment.name,
            )
            for environment in experiment.environments
        }
        known_keys = self._repository.known_sample_keys_by_environment(handle.experiment_id)
        iterators = {
            environment.name: environment.iter_candidate_samples()
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
                    self._repository.record_candidate(
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
        self._repository.mark_pool_entries_selected(
            list(entries),
            sampler_invocation_id=sampler_invocation_id,
        )


def reserve_sample_pool_entries_for_sampler(
    *,
    session: Session,
    experiment_id: UUID,
    k: int,
    candidate_pool_size: int | None,
    sampler_name: str,
    sampler_config: dict[str, JsonValue] | None = None,
) -> tuple[ExperimentSamplerInvocationRow, list[ExperimentSamplePoolEntryRow]]:
    """Reserve existing candidate-pool rows for a trainer sampler.

    Trainer rollout services can ask the experiment application domain for
    already-buffered samples without importing the experiment repository
    directly. Stream replenishment remains the Python authoring API's job.
    """

    experiment = session.get(ExperimentRow, experiment_id)
    if experiment is None:
        raise ValueError(f"Experiment {experiment_id} not found")

    repository = ExperimentRepository(session)
    pool_size = candidate_pool_size or k
    candidates = repository.pending_unselected_pool_entries(experiment_id)
    if len(candidates) < k:
        raise ValueError(
            "Experiment candidate pool does not contain enough unselected samples. "
            "Submit through the Python experiment API to replenish streamed environments."
        )

    config = dict(sampler_config or {})
    selected_entries = _select_candidate_entries(
        candidates[:pool_size],
        k=k,
        sampler_name=sampler_name,
        sampler_config=config,
    )
    invocation = record_sampler_invocation(
        session=session,
        experiment_ref=ExperimentRef(
            experiment_id=experiment.id,
            name=experiment.name,
            environment_ids={},
            created_at=experiment.created_at,
            metadata=experiment.metadata_json,
        ),
        sampler_name=sampler_name,
        requested_k=k,
        candidate_pool_size=pool_size,
        selected_count=len(selected_entries),
        sampler_config=config,
    )
    repository.mark_pool_entries_selected(
        selected_entries,
        sampler_invocation_id=invocation.id,
    )
    return invocation, selected_entries


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
        sample_ref=payload.get("sample_ref")
        if isinstance(payload.get("sample_ref"), dict)
        else None,
        source_metadata=(
            payload.get("source_metadata")
            if isinstance(payload.get("source_metadata"), dict)
            else None
        ),
        metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else None,
    )


async def _task_from_candidate_snapshot(task_json: object) -> Task:
    if not isinstance(task_json, dict):
        raise ValueError(
            f"Candidate task snapshot must be an object, got {type(task_json).__name__}"
        )
    task = await Task.from_definition(task_json, task_id=uuid4())
    # Candidate-pool rows are not runtime materializations. We use the existing
    # `_type` dispatch path to rebuild object-bound config, then clear the
    # temporary id so materialization remains the only runtime-id boundary.
    if isinstance(task.dependency_task_slugs, list):
        task.dependency_task_slugs = tuple(task.dependency_task_slugs)
    if isinstance(task.task_payload, dict) and not task.task_payload:
        task.task_payload = EmptyTaskPayload()
    task._task_id = None
    return task


def _select_candidate_entries(
    entries: Sequence[ExperimentSamplePoolEntryRow],
    *,
    k: int,
    sampler_name: str,
    sampler_config: dict[str, JsonValue],
) -> list[ExperimentSamplePoolEntryRow]:
    selected = list(entries)
    if sampler_name == "random":
        import random

        seed = sampler_config.get("seed")
        if seed is not None and not isinstance(seed, (str, bytes, bytearray, int, float)):
            raise ValueError("Random trainer sampler seed must be a scalar value")
        random.Random(seed).shuffle(selected)
    elif sampler_name not in {"sequential", "all"}:
        raise ValueError(f"Unsupported trainer sampler: {sampler_name}")
    return selected[: min(k, len(selected))]
