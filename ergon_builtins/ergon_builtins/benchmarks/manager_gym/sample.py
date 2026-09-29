"""Build Ergon samples for Manager Gym episodes, and for re-grading frozen snapshots."""

from collections.abc import AsyncGenerator
from typing import ClassVar, cast
from uuid import UUID

from ergon_core.api import Sample, Task, Worker, WorkerContext, WorkerStreamItem
from pydantic import JsonValue

from ergon_builtins.benchmarks.manager_gym.constants import (
    MANAGER_ACTOR_ID,
    PROVIDER,
    RUBRIC_NAME,
    SANDBOX_TIMEOUT_SECONDS,
)
from ergon_builtins.benchmarks.manager_gym.inference import InferenceProfile
from ergon_builtins.benchmarks.manager_gym.manager import EpisodeTask, MAGManagerWorker
from ergon_builtins.benchmarks.manager_gym.rubric import MAGRubric
from ergon_builtins.benchmarks.manager_gym.rubric_versions import (
    LATEST_RUBRIC_VERSION,
    RubricVersion,
)
from ergon_builtins.benchmarks.manager_gym.state import (
    BENCHMARK_VERSION,
    SOURCE_REVISION,
    EpisodeConfig,
    EpisodeState,
    scenario_goal,
    snapshot_hash,
    snapshot_output,
)
from ergon_builtins.sandbox.e2b_sandbox import E2BSandbox


def _source_metadata(
    inference: InferenceProfile, rubric_version: RubricVersion, **extra: str
) -> dict[str, JsonValue]:
    return {
        "provider": PROVIDER,
        "benchmark_version": BENCHMARK_VERSION,
        "source_revision": SOURCE_REVISION,
        "rubric_version": rubric_version,
        **extra,
        "inference_profile": inference.model_dump(mode="json"),
    }


def make_manager_gym_sample(
    config: EpisodeConfig,
    *,
    model: str,
    environment_name: str = "manager-gym",
    rubric_version: RubricVersion = LATEST_RUBRIC_VERSION,
) -> Sample:
    """Build the Ergon sample for one MAG episode.

    Args:
        config: Scenario, manager policy, seed and limits for the episode.
        model: Ergon model target used by every role and by the LLM judge.
        environment_name: Environment the sample is recorded under.
        rubric_version: 1 reproduces upstream scoring; 2 applies the corrections in
            ``rubric_versions.py``.

    Returns:
        A sample with a single manager task, graded by ``MAGRubric``.
    """
    task = EpisodeTask(
        task_slug=f"mag-{config.scenario}",
        instance_key=str(config.seed),
        description=scenario_goal(config.scenario),
        task_payload=config,
        worker=MAGManagerWorker(name="MAG manager", actor_key=MANAGER_ACTOR_ID, model=model),
        sandbox=E2BSandbox(timeout_seconds=SANDBOX_TIMEOUT_SECONDS),
        evaluators=(
            MAGRubric(
                name=RUBRIC_NAME,
                scenario=config.scenario,
                model=model,
                rubric_version=rubric_version,
            ),
        ),
    )
    return Sample.from_tasks(
        name=f"{config.scenario}:{config.seed}",
        sample_key=f"{config.scenario}:{config.seed}",
        environment_name=environment_name,
        sample_ref=config.model_dump(mode="json"),
        source_metadata=_source_metadata(config.inference, rubric_version),
        tasks=[cast(Task, task)],
    )


class SnapshotTask(Task[EpisodeState]):
    """A task whose payload is a frozen episode snapshot."""


class MAGSnapshotWorker(Worker):
    """Re-publishes a frozen snapshot unchanged, so ``MAGRubric`` can grade it again."""

    type_slug: ClassVar[str] = "manager-gym-snapshot"

    async def execute(
        self, task: Task, *, context: WorkerContext
    ) -> AsyncGenerator[WorkerStreamItem]:
        state = EpisodeState.model_validate(task.task_payload.model_dump())
        yield await snapshot_output(state, task.sandbox)


def make_snapshot_reevaluation_sample(
    state: EpisodeState,
    *,
    source_sample_id: UUID,
    environment_name: str,
    model: str,
    rubric_version: RubricVersion = LATEST_RUBRIC_VERSION,
) -> Sample:
    """Build a sample that re-grades a frozen episode snapshot without re-running it.

    Args:
        state: The frozen episode state produced by the manager.
        source_sample_id: The sample the snapshot came from.
        environment_name: Environment the new sample is recorded under.
        model: Ergon model target for the LLM judge.
        rubric_version: Rubric version to grade under; see ``make_manager_gym_sample``.

    Returns:
        A sample whose single task replays the snapshot into ``MAGRubric``.
    """
    scenario = state.config.scenario
    task = SnapshotTask(
        task_slug=f"mag-reevaluate-{scenario}",
        instance_key=str(source_sample_id),
        description=state.workflow.workflow_goal,
        task_payload=state,
        worker=MAGSnapshotWorker(name="Frozen MAG snapshot", model=model),
        sandbox=E2BSandbox(timeout_seconds=SANDBOX_TIMEOUT_SECONDS),
        evaluators=(
            MAGRubric(
                name=RUBRIC_NAME, scenario=scenario, model=model, rubric_version=rubric_version
            ),
        ),
    )
    return Sample.from_tasks(
        name=f"Re-evaluate {scenario}:{source_sample_id}",
        sample_key=f"reevaluate:{source_sample_id}",
        environment_name=environment_name,
        source_metadata=_source_metadata(
            state.config.inference,
            rubric_version,
            evaluation_of_sample=str(source_sample_id),
            snapshot_hash=snapshot_hash(state),
        ),
        tasks=[cast(Task, task)],
    )
