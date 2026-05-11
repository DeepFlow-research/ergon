"""Architecture guards for the Phase 1 public API target structure."""

import importlib
import inspect
import ast
from pathlib import Path


def test_public_api_root_exports_semantic_authoring_names_only() -> None:
    public_api = importlib.import_module("ergon_core.api")

    expected = {
        "Benchmark",
        "BenchmarkRequirements",
        "ContainmentViolation",
        "Task",
        "EmptyTaskPayload",
        "Evaluator",
        "Experiment",
        "Sandbox",
        "SandboxKindMismatch",
        "SandboxNotLiveError",
        "SandboxRuntime",
        "Worker",
        "WorkerContext",
        "WorkerOutput",
        "WorkerStreamItem",
        "SpawnedTaskHandle",
        "Criterion",
        "CriterionContext",
        "CriterionOutcome",
        "CriterionEvidence",
        "EvidenceMessage",
        "Rubric",
        "TaskEvaluationResult",
        "TaskNotMaterializedError",
        "WeightedCriterion",
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
        "ComponentRegistry",
        "WorkerSpec",
        "TaskSpec",
        "PersistedExperimentDefinition",
        "DefinitionHandle",
        "registry",
        "ScoreScale",
    }

    assert set(public_api.__all__) == expected
    assert all(hasattr(public_api, name) for name in expected)
    assert retired.isdisjoint(public_api.__all__)


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
    assert worker.__all__ == [
        "Worker",
        "WorkerContext",
        "WorkerOutput",
        "WorkerStreamItem",
        "SpawnedTaskHandle",
    ]
    assert criterion.__all__ == [
        "Criterion",
        "CriterionContext",
        "CriterionOutcome",
        "CriterionEvidence",
        "EvidenceMessage",
    ]
    assert rubric.__all__ == ["Evaluator", "Rubric", "TaskEvaluationResult", "WeightedCriterion"]


def test_core_composition_owns_definition_handle_only() -> None:
    composition = importlib.import_module("ergon_core.core.domain.experiments")

    assert composition.__all__ == ["DefinitionHandle"]
    assert hasattr(composition, "DefinitionHandle")
    assert not hasattr(composition, "Experiment")
    assert not hasattr(composition, "WorkerSpec")


def test_old_core_experiment_module_stays_deleted() -> None:
    assert importlib.util.find_spec("ergon_core.core.domain.experiments.experiment") is None


def test_definition_serialization_is_not_an_api_private_module() -> None:
    assert importlib.util.find_spec("ergon_core.api._definition") is None
    assert importlib.util.find_spec("ergon_core.core.domain.definitions.serialization") is not None


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
    assert "_runtime" not in context_module.CriterionContext.__private_attributes__
    assert not hasattr(context_module.CriterionContext, "execute_code")
    assert not hasattr(context_module.CriterionContext, "with_runtime")


def test_public_api_uses_shared_json_object_alias() -> None:
    api_root = Path(__file__).parents[3] / "ergon_core" / "api"
    offenders: list[str] = []
    for path in api_root.rglob("*.py"):
        source = path.read_text()
        if "dict[str, Any]" in source:
            offenders.append(str(path.relative_to(api_root)))

    assert offenders == []


def test_public_api_modules_do_not_hide_import_cycles() -> None:
    api_root = Path(__file__).parents[3] / "ergon_core" / "api"
    offenders: list[str] = []
    for path in api_root.rglob("*.py"):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr == "model_rebuild":
                    offenders.append(f"{path.relative_to(api_root)}:{node.lineno}:model_rebuild")
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for child in ast.walk(node):
                    if isinstance(child, (ast.Import, ast.ImportFrom)):
                        offenders.append(f"{path.relative_to(api_root)}:{child.lineno}:function import")

    assert offenders == []


def test_authoring_runtime_deletes_component_catalog_and_definition_pools() -> None:
    persistence_root = Path(__file__).parents[3] / "ergon_core" / "core" / "persistence"
    offenders: list[str] = []
    forbidden = (
        "ComponentCatalog",
        "ComponentCatalogEntry",
        "ExperimentDefinitionWorker",
        "ExperimentDefinitionEvaluator",
        "worker_bindings",
        "evaluator_bindings",
    )

    for path in persistence_root.rglob("*.py"):
        source = path.read_text()
        for snippet in forbidden:
            if snippet in source:
                offenders.append(f"{path.relative_to(persistence_root)}:{snippet}")

    assert offenders == []


def test_authoring_runtime_uses_task_id_without_run_graph_node_identity() -> None:
    persistence_root = Path(__file__).parents[3] / "ergon_core" / "core" / "persistence"
    offenders: list[str] = []
    forbidden = (
        "node_id",
        "run_graph_node_id",
        "definition_task_id",
    )

    for path in persistence_root.rglob("*.py"):
        source = path.read_text()
        for snippet in forbidden:
            if snippet in source:
                offenders.append(f"{path.relative_to(persistence_root)}:{snippet}")

    assert offenders == []


def test_criterion_runtime_indirection_is_deleted() -> None:
    runtime_root = Path(__file__).parents[3] / "ergon_core"
    offenders: list[str] = []
    forbidden = (
        "DefaultCriterionRuntime",
        "CriterionRuntimeOptions",
        "ScoreScale",
        "score_spec",
    )

    for path in runtime_root.rglob("*.py"):
        if path.name == "test_public_api_target_structure.py":
            continue
        source = path.read_text()
        for snippet in forbidden:
            if snippet in source:
                offenders.append(f"{path.relative_to(runtime_root)}:{snippet}")

    assert offenders == []


def test_legacy_sandbox_manager_modules_are_deleted() -> None:
    runtime_root = Path(__file__).parents[3] / "ergon_core"
    offenders: list[str] = []
    forbidden = (
        "BaseSandboxManager",
        "SandboxManager",
        "sandbox_manager",
    )

    for path in runtime_root.rglob("*.py"):
        if path.name == "test_public_api_target_structure.py":
            continue
        source = path.read_text()
        for snippet in forbidden:
            if snippet in source:
                offenders.append(f"{path.relative_to(runtime_root)}:{snippet}")

    assert offenders == []
