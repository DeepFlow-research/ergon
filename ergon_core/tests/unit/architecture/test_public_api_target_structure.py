"""Architecture guards for the Phase 1 public API target structure."""

import importlib
import inspect


def test_public_api_root_exports_semantic_authoring_names_only() -> None:
    public_api = importlib.import_module("ergon_core.api")

    expected = {
        "Benchmark",
        "BenchmarkRequirements",
        "Task",
        "EmptyTaskPayload",
        "Worker",
        "WorkerContext",
        "WorkerOutput",
        "WorkerStreamItem",
        "AwaitCompletionNotSupportedError",
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
        # PR 6.5 — Experiment wrapper deleted; persist_benchmark replaces it.
        "Evaluator",
        "persist_benchmark",
        "Rubric",
        "Sandbox",
        "SandboxKindMismatch",
        "SandboxRuntime",
        "SandboxNotLiveError",
        "TaskEvaluationResult",
        "CriterionCheckError",
    }
    retired = {
        "BenchmarkTask",
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


def test_semantic_api_clusters_are_importable() -> None:
    benchmark = importlib.import_module("ergon_core.api.benchmark")
    worker = importlib.import_module("ergon_core.api.worker")
    criterion = importlib.import_module("ergon_core.api.criterion")
    rubric = importlib.import_module("ergon_core.api.rubric")

    assert benchmark.__all__ == [
        "Benchmark",
        "BenchmarkRequirements",
        "Task",
        "EmptyTaskPayload",
    ]
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
        importlib.import_module("ergon_core.api.criterion.results"),
        importlib.import_module("ergon_core.api.rubric.results"),
    ]

    assert all(
        "ergon_core.core.shared.json_types" not in inspect.getsource(module) for module in modules
    )
