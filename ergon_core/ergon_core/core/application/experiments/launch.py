"""Experiment launch service."""

from collections.abc import Awaitable, Callable, Mapping, Sequence
from uuid import UUID

import inngest
from ergon_core.api.benchmark import Benchmark
from ergon_core.api.registry import registry
from ergon_core.api.rubric import Evaluator
from ergon_core.core.domain.experiments import Experiment
from ergon_core.core.domain.experiments import DefinitionHandle
from ergon_core.core.shared.json_types import JsonObject, JsonValue
from ergon_core.api.benchmark import TaskSpec
from ergon_core.core.domain.experiments import WorkerSpec
from ergon_core.core.persistence.definitions.models import ExperimentDefinition
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.telemetry.models import BenchmarkDefinitionRecord
from ergon_core.core.application.events.task_events import WorkflowStartedEvent
from ergon_core.core.infrastructure.inngest.client import inngest_client
from ergon_core.core.application.experiments.models import (
    ExperimentRunRequest,
    ExperimentRunResult,
    RunAssignment,
)
from ergon_core.core.application.experiments.definition_writer import _ExperimentDefinitionWriter

from ergon_core.core.application.workflows.runs import create_run
from pydantic import BaseModel

WorkflowDefinitionFactory = Callable[
    [BenchmarkDefinitionRecord, RunAssignment],
    DefinitionHandle,
]
WorkflowStartedEmitter = Callable[[UUID, UUID], Awaitable[None]]


async def launch_run(
    definition_id: UUID,
    *,
    metadata: Mapping[str, JsonValue] | None = None,
    emit_workflow_started: WorkflowStartedEmitter | None = None,
) -> ExperimentRunResult:
    """Materialize a run directly from an ``ExperimentDefinition`` row.

    The canonical definition-first launch path introduced in PR 7. Skips the
    legacy ``BenchmarkDefinitionRecord`` lookup entirely — identity comes
    from ``ExperimentDefinition``. PR 11 narrows ``create_run`` so the
    ``experiment_id=None`` / ``instance_key=None`` calls land cleanly.
    """
    emitter = emit_workflow_started or _emit_workflow_started
    with get_session() as session:
        definition = session.get(ExperimentDefinition, definition_id)
        if definition is None:
            raise ValueError(f"ExperimentDefinition {definition_id} not found")
        run = create_run(
            DefinitionHandle(
                definition_id=definition.id,
                benchmark_type=definition.benchmark_type,
            ),
            experiment_id=None,  # type: ignore[arg-type]  # PR 11 narrows create_run; legacy FK still nominally required
            workflow_definition_id=definition.id,
            instance_key=None,  # type: ignore[arg-type]  # PR 11 narrows create_run; legacy column still nominally required
            worker_team_json={},
            evaluator_slug=None,
            model_target=None,
            sandbox_slug=None,
            dependency_extras_json={},
            assignment_json=dict(metadata or {}),
            seed=None,
        )
    await emitter(run.id, definition_id)
    return ExperimentRunResult(
        experiment_id=definition_id,
        run_ids=[run.id],
        workflow_definition_ids=[definition_id],
    )


class _ExperimentRunLauncher:
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
            experiment = session.get(BenchmarkDefinitionRecord, request.experiment_id)
            if experiment is None:
                raise ValueError(f"Experiment {request.experiment_id} not found")
            assignments = _assign_runs(experiment)
            experiment.status = "running"
            session.add(experiment)
            session.commit()
            session.refresh(experiment)

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
                sandbox_slug=assignment.sandbox_slug,
                dependency_extras_json={"extras": list(assignment.dependency_extras)},
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


def _assign_runs(experiment: BenchmarkDefinitionRecord) -> list[RunAssignment]:
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
            evaluator_bindings=_evaluator_binding_slugs(experiment),
            model_target=experiment.default_model_target,
            sandbox_slug=experiment.sandbox_slug,
            dependency_extras=tuple(experiment.parsed_dependency_extras().get("extras", ())),
            arm_key="default",
            seed=experiment.seed,
            metadata={"arm_key": "default"},
        )
        for instance_key in instance_keys
    ]


def _persist_single_sample_workflow_definition(
    experiment: BenchmarkDefinitionRecord,
    assignment: RunAssignment,
) -> DefinitionHandle:
    benchmark_slug = _metadata_str(experiment, "benchmark_slug") or experiment.benchmark_type
    benchmark = _single_sample_benchmark(benchmark_slug, assignment.instance_key)
    worker_slug = _primary_worker_slug(assignment.worker_team)
    worker = WorkerSpec(
        worker_slug=worker_slug,
        name="primary",
        model=assignment.model_target or "openai:gpt-4o",
    )
    evaluators = _evaluator_bindings(assignment.evaluator_slug, assignment.evaluator_bindings)
    workflow = Experiment.from_single_worker(
        benchmark=benchmark,
        worker=worker,
        evaluators=evaluators,
    )
    workflow.validate()
    return _ExperimentDefinitionWriter().persist_definition(workflow)


def _metadata_str(experiment: BenchmarkDefinitionRecord, key: str) -> str | None:
    value = experiment.parsed_metadata().get(key)
    return value if isinstance(value, str) else None


def _primary_worker_slug(worker_team: JsonObject) -> str:
    value = worker_team.get("primary")
    if not isinstance(value, str) or not value:
        raise ValueError("Run assignment worker_team requires a string 'primary' worker slug")
    return value


def _evaluator_binding_slugs(experiment: BenchmarkDefinitionRecord) -> dict[str, str]:
    design = experiment.design_json or {}
    bindings = design.get("evaluator_bindings")
    if not isinstance(bindings, dict):
        return {}
    return {
        key: value
        for key, value in bindings.items()
        if isinstance(key, str) and isinstance(value, str)
    }


def _evaluator_bindings(
    evaluator_slug: str | None,
    evaluator_binding_slugs: Mapping[str, str],
) -> dict[str, Evaluator]:
    evaluators: dict[str, Evaluator] = {}
    if evaluator_slug is None:
        return evaluators
    evaluator_cls = registry.require_evaluator(evaluator_slug)
    evaluators["default"] = evaluator_cls(name="default")
    for binding_key, bound_evaluator_slug in evaluator_binding_slugs.items():
        if binding_key == "default":
            continue
        bound_evaluator_cls = registry.require_evaluator(bound_evaluator_slug)
        evaluators[binding_key] = bound_evaluator_cls(name=binding_key)
    return evaluators


def _single_sample_benchmark(benchmark_slug: str, instance_key: str) -> Benchmark:
    source = registry.require_benchmark(benchmark_slug)()
    instances = source.build_instances()
    if instance_key not in instances:
        raise ValueError(
            f"Experiment sample {instance_key!r} not found in benchmark {benchmark_slug!r}"
        )
    wrapper_cls = _single_sample_benchmark_cls(source)
    return wrapper_cls(source, instance_key, instances[instance_key])


class _SingleSampleBenchmark(Benchmark):
    type_slug = "single-sample-wrapper"

    def __init__(
        self,
        source: Benchmark,
        instance_key: str,
        tasks: Sequence[TaskSpec[BaseModel]],
    ) -> None:
        super().__init__(
            name=source.name,
            description=source.description,
            metadata=source.metadata,
        )
        self._source = source
        self._instance_key = instance_key
        self._tasks = list(tasks)

    def build_instances(self) -> Mapping[str, Sequence[TaskSpec[BaseModel]]]:
        return {self._instance_key: self._tasks}

    def evaluator_requirements(self) -> Sequence[str]:
        return self._source.evaluator_requirements()


def _single_sample_benchmark_cls(source: Benchmark) -> type[_SingleSampleBenchmark]:
    return type(
        f"SingleSample{source.type_slug.replace('-', '_').title()}Benchmark",
        (_SingleSampleBenchmark,),
        {
            "type_slug": source.type_slug,
            "task_payload_model": source.task_payload_model,
            "required_packages": source.required_packages,
            "install_hint": source.install_hint,
        },
    )


async def _emit_workflow_started(run_id: UUID, definition_id: UUID) -> None:
    event = WorkflowStartedEvent(run_id=run_id, definition_id=definition_id)
    await inngest_client.send(
        inngest.Event(
            name=WorkflowStartedEvent.name,
            data=event.model_dump(mode="json"),
        )
    )
