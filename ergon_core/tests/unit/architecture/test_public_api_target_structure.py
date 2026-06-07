"""Architecture guards for the Phase 1 public API target structure."""

from abc import ABC
import importlib
import inspect

import pytest


def test_public_api_root_exports_semantic_authoring_names_only() -> None:
    public_api = importlib.import_module("ergon_core.api")

    expected = {
        "Task",
        "EmptyTaskPayload",
        "Environment",
        "Experiment",
        "ExperimentSubmitResult",
        "PersistedExperiment",
        "Worker",
        "WorkerContext",
        "WorkerOutput",
        "WorkerStreamItem",
        "AwaitCompletionNotSupportedError",
        "DependencyError",
        # PR 9 — dynamic subtasks: SpawnedTaskHandle is the return type
        # of ``WorkerContext.spawn_task`` / ``.restart_task``;
        # ContainmentViolation is raised by the curated single-target
        # facade methods when a worker targets a task it does not own.
        "SpawnedTaskHandle",
        "ContainmentViolation",
        "Criterion",
        "CriterionContext",
        "CriterionOutcome",
        "ScoreScale",
        "CriterionEvidence",
        "EvidenceMessage",
        # PR 5 — object-bound authoring surface.
        "Evaluator",
        "RandomSampler",
        "Rubric",
        "Sample",
        "Sandbox",
        "SandboxKindMismatch",
        "SandboxRuntime",
        "SandboxNotLiveError",
        "Sampler",
        "SamplingContext",
        "TaskEvaluationResult",
        "CriterionCheckError",
    }
    retired = {
        "BenchmarkTask",
        "Benchmark",
        "BenchmarkDeps",
        "EvaluationContext",
        "CriterionResult",
        "CriterionScoreSpec",
        "CriterionObservation",
        "CriterionObservationMessage",
        "CriteriaCheckError",
        "WorkerSpec",
        "PersistedExperimentDefinition",
        "DefinitionHandle",
        "Episode",
        "EnvironmentSource",
        "ExperimentHandle",
        "ExperimentRunHandle",
        "persist_benchmark",
        "persist_experiment",
        "SourceDescriptor",
        # Toolkit is a ReAct/builtins implementation detail, not a core
        # authoring API concept.
        "Toolkit",
        "ComponentCatalog",
        "registry",
    }

    assert set(public_api.__all__) == expected
    assert all(hasattr(public_api, name) for name in expected)
    assert retired.isdisjoint(public_api.__all__)
    assert all(not hasattr(public_api, name) for name in retired)


def test_experiment_public_api_does_not_export_service_ports() -> None:
    public_api = importlib.import_module("ergon_core.api")
    experiment_api = importlib.import_module("ergon_core.api.experiment")

    forbidden = {
        "ExperimentSubmissionPort",
        "PersistExperimentPort",
        "SamplingHistory",
    }

    for module in (public_api, experiment_api):
        for name in forbidden:
            assert not hasattr(module, name), f"{module.__name__} exports {name}"


def test_sampler_is_public_abstract_base_model() -> None:
    from pydantic import BaseModel

    from ergon_core.api import RandomSampler, Sampler

    assert issubclass(Sampler, BaseModel)
    assert issubclass(Sampler, ABC)
    assert issubclass(RandomSampler, Sampler)


def test_persisted_experiment_is_the_public_persistence_receipt() -> None:
    public_api = importlib.import_module("ergon_core.api")

    assert hasattr(public_api, "PersistedExperiment")
    assert not hasattr(public_api, "ExperimentRef")


def test_semantic_api_clusters_are_importable() -> None:
    task = importlib.import_module("ergon_core.api.task")
    worker = importlib.import_module("ergon_core.api.worker")
    criterion = importlib.import_module("ergon_core.api.criterion")
    rubric = importlib.import_module("ergon_core.api.rubric")

    assert task.Task.__module__ == "ergon_core.api.task"
    assert task.EmptyTaskPayload.__module__ == "ergon_core.api.task"
    # PR 9 Task 1 added ``SpawnedTaskHandle`` to the worker cluster as
    # the return type of ``WorkerContext.spawn_task`` and
    # ``WorkerContext.restart_task``.
    assert worker.__all__ == [
        "AwaitCompletionNotSupportedError",
        "SpawnedTaskHandle",
        "Worker",
        "WorkerContext",
        "WorkerOutput",
        "WorkerStreamItem",
    ]
    assert criterion.__all__ == [
        "Criterion",
        "CriterionContext",
        "CriterionOutcome",
        "ScoreScale",
        "CriterionEvidence",
        "EvidenceMessage",
    ]
    assert rubric.__all__ == ["Evaluator", "Rubric", "TaskEvaluationResult"]


def test_public_worker_module_does_not_import_persistence_or_sessions() -> None:
    worker_module = importlib.import_module("ergon_core.api.worker.worker")
    source = inspect.getsource(worker_module)

    forbidden = (
        "ergon_core.core.persistence",
        "ContextEventService",
        "get_session",
        "sqlmodel",
    )
    assert all(snippet not in source for snippet in forbidden)


def test_criterion_context_hides_runtime_protocol_field() -> None:
    context_module = importlib.import_module("ergon_core.api.criterion.context")
    context_fields = context_module.CriterionContext.model_fields

    assert "runtime" not in context_fields
    assert "task" in context_fields


def test_public_result_models_do_not_import_core_json_types() -> None:
    modules = [
        importlib.import_module("ergon_core.api.worker.results"),
        importlib.import_module("ergon_core.api.criterion.score"),
        importlib.import_module("ergon_core.api.criterion.evidence"),
        importlib.import_module("ergon_core.api.criterion.outcome"),
        importlib.import_module("ergon_core.api.rubric.results"),
    ]

    assert all(
        "ergon_core.core.shared.json_types" not in inspect.getsource(module) for module in modules
    )


def test_legacy_criterion_results_module_is_absent() -> None:
    module_name = ".".join(["ergon_core", "api", "criterion", "results"])
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(module_name)
