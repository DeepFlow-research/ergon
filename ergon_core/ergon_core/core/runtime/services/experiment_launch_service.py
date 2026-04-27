"""Experiment launch service."""

from collections.abc import Awaitable, Callable, Mapping, Sequence
from uuid import UUID

import inngest
from ergon_core.api.benchmark import Benchmark
from ergon_core.api.evaluator import Evaluator
from ergon_core.api.experiment import Experiment
from ergon_core.api.handles import PersistedExperimentDefinition
from ergon_core.api.task_types import BenchmarkTask
from ergon_core.api.worker_spec import WorkerSpec
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.telemetry.models import ExperimentRecord
from ergon_core.core.runtime.events.task_events import WorkflowStartedEvent
from ergon_core.core.runtime.inngest_client import inngest_client
from ergon_core.core.runtime.services.experiment_schemas import (
    ExperimentRunRequest,
    ExperimentRunResult,
    RunAssignment,
)
from ergon_core.core.runtime.services.run_service import create_run
from pydantic import BaseModel

WorkflowDefinitionFactory = Callable[
    [ExperimentRecord, RunAssignment],
    PersistedExperimentDefinition,
]
WorkflowStartedEmitter = Callable[[UUID, UUID], Awaitable[None]]


class ExperimentLaunchService:
    """Materialize runs for a previously defined experiment."""

    def __init__(
        self,
        *,
        workflow_definition_factory: WorkflowDefinitionFactory | None = None,
        emit_workflow_started: WorkflowStartedEmitter | None = None,
    ) -> None:
        self._workflow_definition_factory = (
            workflow_definition_factory or _persist_single_sample_workflow_definition
        )
        self._emit_workflow_started = emit_workflow_started or _emit_workflow_started

    async def run_experiment(self, request: ExperimentRunRequest) -> ExperimentRunResult:
        with get_session() as session:
            experiment = session.get(ExperimentRecord, request.experiment_id)
            if experiment is None:
                raise ValueError(f"Experiment {request.experiment_id} not found")
            assignments = _assign_runs(experiment)
            experiment.status = "running"
            session.add(experiment)
            session.commit()

        run_ids: list[UUID] = []
        workflow_definition_ids: list[UUID] = []
        for assignment in assignments:
            definition = self._workflow_definition_factory(experiment, assignment)
            run = create_run(
                definition,
                experiment_id=experiment.id,
                workflow_definition_id=definition.definition_id,
                instance_key=assignment.instance_key,
                worker_team_json=assignment.worker_team,
                evaluator_slug=assignment.evaluator_slug,
                model_target=assignment.model_target,
                assignment_json=assignment.metadata,
                seed=assignment.seed,
            )
            await self._emit_workflow_started(run.id, definition.definition_id)
            run_ids.append(run.id)
            workflow_definition_ids.append(definition.definition_id)

        return ExperimentRunResult(
            experiment_id=experiment.id,
            run_ids=run_ids,
            workflow_definition_ids=workflow_definition_ids,
        )


def _assign_runs(experiment: ExperimentRecord) -> list[RunAssignment]:
    sample_selection = experiment.parsed_sample_selection()
    instance_keys = sample_selection.get("instance_keys")
    if not isinstance(instance_keys, list) or not all(
        isinstance(instance_key, str) for instance_key in instance_keys
    ):
        raise ValueError("Experiment sample_selection_json must include string instance_keys")

    return [
        RunAssignment(
            instance_key=instance_key,
            sample_id=instance_key,
            worker_team=experiment.parsed_default_worker_team(),
            evaluator_slug=experiment.default_evaluator_slug,
            model_target=experiment.default_model_target,
            arm_key="default",
            seed=experiment.seed,
            metadata={"arm_key": "default"},
        )
        for instance_key in instance_keys
    ]


def _persist_single_sample_workflow_definition(
    experiment: ExperimentRecord,
    assignment: RunAssignment,
) -> PersistedExperimentDefinition:
    benchmark_slug = _metadata_str(experiment, "benchmark_slug") or experiment.benchmark_type
    benchmark = _single_sample_benchmark(benchmark_slug, assignment.instance_key)
    worker_slug = _primary_worker_slug(assignment.worker_team)
    worker = WorkerSpec(
        worker_slug=worker_slug,
        name="primary",
        model=assignment.model_target or "openai:gpt-4o",
    )
    evaluators = _evaluator_bindings(assignment.evaluator_slug)
    workflow = Experiment.from_single_worker(
        benchmark=benchmark,
        worker=worker,
        evaluators=evaluators,
    )
    return workflow.persist()


def _metadata_str(experiment: ExperimentRecord, key: str) -> str | None:
    value = experiment.parsed_metadata().get(key)
    return value if isinstance(value, str) else None


def _primary_worker_slug(worker_team: Mapping[str, object]) -> str:
    value = worker_team.get("primary")
    if not isinstance(value, str) or not value:
        raise ValueError("Run assignment worker_team requires a string 'primary' worker slug")
    return value


def _evaluator_bindings(evaluator_slug: str | None) -> dict[str, Evaluator]:
    if evaluator_slug is None:
        return {}
    from ergon_builtins.registry import EVALUATORS

    evaluator_cls = EVALUATORS[evaluator_slug]
    return {"default": evaluator_cls(name="evaluator")}


def _single_sample_benchmark(benchmark_slug: str, instance_key: str) -> Benchmark:
    from ergon_builtins.registry import BENCHMARKS

    source = BENCHMARKS[benchmark_slug]()
    instances = source.build_instances()
    if instance_key not in instances:
        raise ValueError(
            f"Experiment sample {instance_key!r} not found in benchmark {benchmark_slug!r}"
        )
    return _SingleSampleBenchmark(source, instance_key, instances[instance_key])


class _SingleSampleBenchmark(Benchmark):
    type_slug = "single-sample-wrapper"

    def __init__(
        self,
        source: Benchmark,
        instance_key: str,
        tasks: Sequence[BenchmarkTask[BaseModel]],
    ) -> None:
        super().__init__(
            name=source.name,
            description=source.description,
            metadata=source.metadata,
        )
        self.type_slug = source.type_slug
        self.task_payload_model = source.task_payload_model
        self.required_packages = source.required_packages
        self.install_hint = source.install_hint
        self._source = source
        self._instance_key = instance_key
        self._tasks = list(tasks)

    def build_instances(self) -> Mapping[str, Sequence[BenchmarkTask[BaseModel]]]:
        return {self._instance_key: self._tasks}

    def evaluator_requirements(self) -> Sequence[str]:
        return self._source.evaluator_requirements()


async def _emit_workflow_started(run_id: UUID, definition_id: UUID) -> None:
    event = WorkflowStartedEvent(run_id=run_id, definition_id=definition_id)
    await inngest_client.send(
        inngest.Event(
            name=WorkflowStartedEvent.name,
            data=event.model_dump(mode="json"),
        )
    )

