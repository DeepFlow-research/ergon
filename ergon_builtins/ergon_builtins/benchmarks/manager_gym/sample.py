"""Ordinary Ergon sample construction for the pinned MAG scenario catalog."""

from collections.abc import AsyncGenerator
from typing import ClassVar, cast
from uuid import UUID
from ergon_core.api import Sample, Task, Worker, WorkerContext, WorkerStreamItem
from ergon_core.api.worker import WorkerOutput
from ergon_builtins.sandbox.e2b_sandbox import E2BSandbox
from ergon_builtins.benchmarks.manager_gym.inference import (
    INTERNAL_MODEL,
    require_internal_model,
    inference_profile,
)
from ergon_builtins.benchmarks.manager_gym.manager import EpisodeTask, MAGManagerWorker
from ergon_builtins.benchmarks.manager_gym.rubric import MAGRubric
from ergon_builtins.benchmarks.manager_gym.state import (
    EpisodeConfig,
    EpisodeState,
    snapshot_hash,
    BENCHMARK_VERSION,
    SOURCE_REVISION,
)
from ergon_builtins.benchmarks.manager_gym.scenario_catalog import SCENARIOS


def make_manager_gym_sample(
    config: EpisodeConfig, *, environment_name: str = "manager-gym", model: str = INTERNAL_MODEL
) -> Sample:
    require_internal_model(model)
    spec = SCENARIOS[config.scenario]
    task = EpisodeTask(
        task_slug=f"mag-{config.scenario}",
        instance_key=str(config.seed),
        description=spec.create_workflow().workflow_goal,
        task_payload=config,
        worker=MAGManagerWorker(name="MAG manager", actor_key="manager_agent", model=model),
        sandbox=E2BSandbox(timeout_seconds=3600),
        evaluators=(MAGRubric(name="MAG terminal utility", scenario=config.scenario, model=model),),
    )
    return Sample.from_tasks(
        name=f"{config.scenario}:{config.seed}",
        sample_key=f"{config.scenario}:{config.seed}",
        environment_name=environment_name,
        sample_ref=config.model_dump(mode="json"),
        source_metadata={
            "provider": "ergon-builtin:manager-gym",
            "benchmark_version": BENCHMARK_VERSION,
            "source_revision": SOURCE_REVISION,
            "inference_profile": inference_profile(),
        },
        tasks=[cast(Task, task)],
    )


class SnapshotTask(Task[EpisodeState]):
    pass


class MAGSnapshotWorker(Worker):
    type_slug: ClassVar[str] = "manager-gym-snapshot"

    async def execute(
        self, task: Task, *, context: WorkerContext
    ) -> AsyncGenerator[WorkerStreamItem, None]:
        state = EpisodeState.model_validate(task.task_payload.model_dump())
        encoded = state.model_dump_json()
        await task.sandbox.write_file(
            "/workspace/final_output/manager-gym-snapshot.json", encoded.encode()
        )
        yield WorkerOutput(
            output=encoded,
            metadata={
                "snapshot_hash": snapshot_hash(state),
                "incomplete": bool(state.infrastructure_errors),
                "benchmark_version": BENCHMARK_VERSION,
                "source_revision": SOURCE_REVISION,
            },
        )


def make_snapshot_reevaluation_sample(
    state: EpisodeState,
    *,
    source_sample_id: UUID,
    environment_name: str,
    model: str = INTERNAL_MODEL,
) -> Sample:
    require_internal_model(model)
    return Sample.from_tasks(
        name=f"Re-evaluate {state.config.scenario}:{source_sample_id}",
        sample_key=f"reevaluate:{source_sample_id}",
        environment_name=environment_name,
        source_metadata={
            "provider": "ergon-builtin:manager-gym",
            "benchmark_version": BENCHMARK_VERSION,
            "source_revision": SOURCE_REVISION,
            "evaluation_of_sample": str(source_sample_id),
            "snapshot_hash": snapshot_hash(state),
            "inference_profile": inference_profile(),
        },
        tasks=[
            cast(
                Task,
                SnapshotTask(
                    task_slug=f"mag-reevaluate-{state.config.scenario}",
                    instance_key=str(source_sample_id),
                    description=state.workflow.workflow_goal,
                    task_payload=state,
                    worker=MAGSnapshotWorker(name="Frozen MAG snapshot", model=model),
                    sandbox=E2BSandbox(timeout_seconds=3600),
                    evaluators=(
                        MAGRubric(
                            name="MAG terminal utility", scenario=state.config.scenario, model=model
                        ),
                    ),
                ),
            )
        ],
    )
