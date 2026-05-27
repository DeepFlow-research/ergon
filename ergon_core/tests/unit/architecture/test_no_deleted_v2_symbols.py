"""Architecture guards for symbols removed from the v2/sample stack."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
PRODUCTION_ROOTS = (
    ROOT / "ergon_core" / "ergon_core",
    ROOT / "ergon_builtins" / "ergon_builtins",
    ROOT / "ergon_cli" / "ergon_cli",
    ROOT / "ergon-dashboard" / "src",
)
PRODUCTION_SUFFIXES = {".py", ".ts", ".tsx"}
DELETED_SYMBOLS = (
    "TaskSpec",
    "ComponentRegistry",
    "ComponentCatalog",
    "ComponentCatalogService",
    "EvaluateTaskRunRequest",
    "ExperimentRecord",
    "CriterionExecutor",
    "InngestCriterionExecutor",
    "definition_task_id",
    "ExperimentDefinition",
    "ExperimentDefinitionTask",
    "ExperimentDefinitionWorker",
    "ExperimentDefinitionEvaluator",
    "definition_id",
    "definition_worker_id",
    "definition_evaluator_id",
    "definition_dependency_id",
    "persistence.definitions",
    "initialize_from_definition",
    "definition_id_for_run",
    "create_definition_backed_sample",
    "persist_benchmark",
    "launch_run",
    "run_experiment",
    "BenchmarkRequirements",
    "parent_node_id",
    "source_node_id",
    "target_node_id",
    "terminate_sandbox_by_id",
)
DELETED_FRONTEND_CONTRACT_TOKENS = (
    "graph:mutation",
    "GraphMutationDto",
    "DashboardGraphMutationData",
    "sampleRuntimeEventsToGraphMutations",
    "Run Index",
    "Search runs",
    "No runs",
)
RUNTIME_VOCABULARY_FORBIDDEN_TOKENS = (
    "RunEvent",
    "RunSnapshot",
    "RunSummary",
    "RunList",
    "RunId",
    "RunLifecycleStatus",
    "RunCommunication",
    "RunExecution",
    "RunEvaluation",
    "RunSandbox",
    "RunHeader",
    "RunActivity",
    "RunAssignment",
    "RunCompletionData",
    "RunCompletedSocketData",
    "run_id",
    "runId",
    "buildRunEvents",
    "broadcastRun",
    "parseRunCompletedSocketData",
    "RunCompletedSocketDataSchema",
    "serializeRunState",
    "request:run",
    "request:runs",
    "sync:run",
    "sync:runs",
    "run:started",
    "run:completed",
    "run-cleanup",
    "cleanup-run",
    "core.jobs.run.cleanup",
)
GENERATED_SCHEMA_FORBIDDEN_TOKENS = (
    "RunCommunication",
    "RunEvaluation",
    "RunExecution",
    "RunSandbox",
)


def _production_files() -> list[Path]:
    files: list[Path] = []
    for root in PRODUCTION_ROOTS:
        for path in root.rglob("*"):
            if ".test." in path.name or path.name.endswith(".test.py"):
                continue
            if path.suffix in PRODUCTION_SUFFIXES:
                files.append(path)
    return files


def test_deleted_v2_symbols_do_not_reappear() -> None:
    hits: list[str] = []
    for path in _production_files():
        text = path.read_text()
        for symbol in DELETED_SYMBOLS:
            if symbol in text:
                hits.append(f"{path.relative_to(ROOT)}: {symbol}")
    assert hits == []


def test_runtime_vocabulary_is_sample_centered_in_production() -> None:
    hits: list[str] = []
    for path in _production_files():
        text = path.read_text()
        for token in RUNTIME_VOCABULARY_FORBIDDEN_TOKENS:
            if token in text:
                hits.append(f"{path.relative_to(ROOT)}: {token}")
    assert hits == []


def test_generated_dashboard_schemas_are_sample_centered() -> None:
    schema_roots = (
        ROOT / "ergon-dashboard" / "src" / "generated" / "events" / "schemas",
        ROOT / "ergon-dashboard" / "src" / "generated" / "rest",
    )
    hits: list[str] = []
    for root in schema_roots:
        for path in root.rglob("*.json"):
            text = path.read_text()
            for token in GENERATED_SCHEMA_FORBIDDEN_TOKENS:
                if token in text:
                    hits.append(f"{path.relative_to(ROOT)}: {token}")
    assert hits == []


def test_dashboard_contracts_do_not_keep_graph_mutation_or_run_vocab_bridges() -> None:
    hits: list[str] = []
    dashboard_root = ROOT / "ergon-dashboard" / "src"
    for path in dashboard_root.rglob("*"):
        if path.suffix not in {".ts", ".tsx"} or ".test." in path.name:
            continue
        text = path.read_text()
        for token in DELETED_FRONTEND_CONTRACT_TOKENS:
            if token in text:
                hits.append(f"{path.relative_to(ROOT)}: {token}")
    assert hits == []
