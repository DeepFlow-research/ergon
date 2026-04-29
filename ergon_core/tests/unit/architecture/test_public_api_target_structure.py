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
        "Criterion",
        "CriterionContext",
        "CriterionOutcome",
        "ScoreScale",
        "CriterionEvidence",
        "EvidenceMessage",
        "Rubric",
        "TaskEvaluationResult",
        "CriterionCheckError",
        "ComponentRegistry",
        "WorkerFactory",
        "registry",
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
        "Experiment",
        "WorkerSpec",
        "PersistedExperimentDefinition",
        "DefinitionHandle",
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

    assert benchmark.__all__ == ["Benchmark", "BenchmarkRequirements", "Task", "EmptyTaskPayload"]
    assert worker.__all__ == ["Worker", "WorkerContext", "WorkerOutput", "WorkerStreamItem"]
    assert criterion.__all__ == [
        "Criterion",
        "CriterionContext",
        "CriterionOutcome",
        "ScoreScale",
        "CriterionEvidence",
        "EvidenceMessage",
    ]
    assert rubric.__all__ == ["Evaluator", "Rubric", "TaskEvaluationResult"]


def test_core_composition_owns_experiment_worker_spec_and_definition_handle() -> None:
    composition = importlib.import_module("ergon_core.core.domain.experiments")

    assert composition.__all__ == ["DefinitionHandle", "Experiment", "WorkerSpec"]
    assert hasattr(composition, "DefinitionHandle")
    assert hasattr(composition, "Experiment")
    assert hasattr(composition, "WorkerSpec")


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
    assert hasattr(context_module.CriterionContext, "execute_code")


def test_public_result_models_do_not_import_core_json_types() -> None:
    modules = [
        importlib.import_module("ergon_core.api.worker.results"),
        importlib.import_module("ergon_core.api.criterion.results"),
        importlib.import_module("ergon_core.api.rubric.results"),
    ]

    assert all("ergon_core.core.shared.json_types" not in inspect.getsource(module) for module in modules)
