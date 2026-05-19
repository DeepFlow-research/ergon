import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]

CONFIG_REFERENCE_FILES = (
    ROOT / "pyproject.toml",
    ROOT / "Dockerfile",
    ROOT / "docker-compose.yml",
)


def test_graph_status_literals_are_defined_only_in_runtime_status() -> None:
    offenders: list[str] = []
    duplicate_snippets = (
        'Literal["pending", "ready", "running", "completed", "failed", "cancelled", "blocked"]',
        'Literal["pending", "ready", "running", "completed", "failed", "blocked", "cancelled"]',
        'Literal["pending", "satisfied", "invalidated"]',
    )
    allowed = {
        ROOT / "ergon_core/ergon_core/core/application/runtime/status.py",
    }

    for path in (ROOT / "ergon_core/ergon_core/core").rglob("*.py"):
        if path in allowed:
            continue
        text = path.read_text()
        compact_text = "".join(text.split()).replace(",]", "]")
        for snippet in duplicate_snippets:
            if snippet in text or "".join(snippet.split()) in compact_text:
                offenders.append(f"{path.relative_to(ROOT)} duplicates {snippet}")

    assert offenders == []


def test_eval_criterion_status_literal_is_defined_only_in_evaluation_summary() -> None:
    offenders: list[str] = []
    snippet = 'EvalCriterionStatus=Literal["passed","failed","errored","skipped"]'
    allowed = {
        ROOT / "ergon_core/ergon_core/core/application/evaluation/summary.py",
    }

    for path in (ROOT / "ergon_core/ergon_core/core").rglob("*.py"):
        if path in allowed:
            continue
        compact_text = "".join(path.read_text().split()).replace(",]", "]")
        if snippet in compact_text:
            offenders.append(str(path.relative_to(ROOT)))

    assert offenders == []


def test_run_task_dto_does_not_label_worker_slug_as_name() -> None:
    path = ROOT / "ergon_core/ergon_core/core/views/runs/models.py"
    text = path.read_text()
    assert "assigned_worker_name" not in text
    assert "assigned_worker_slug" in text


def test_workflow_task_ref_does_not_duplicate_graph_task_ref() -> None:
    path = ROOT / "ergon_core/ergon_core/core/application/workflows/models.py"
    assert "class WorkflowTaskRef" not in path.read_text()


def test_cancel_cause_literals_live_in_task_events() -> None:
    offenders: list[str] = []
    snippets = (
        'Literal["parent_terminal", "dep_invalidated"]',
        'Literal["dep_invalidated", "parent_terminal"]',
    )
    allowed = {
        ROOT / "ergon_core/ergon_core/core/application/events/task_events.py",
    }

    for path in (ROOT / "ergon_core/ergon_core/core").rglob("*.py"):
        if path in allowed:
            continue
        text = path.read_text()
        compact_text = "".join(text.split()).replace(",]", "]")
        for snippet in snippets:
            if snippet in text or "".join(snippet.split()) in compact_text:
                offenders.append(f"{path.relative_to(ROOT)} duplicates cancel cause subset")

    assert offenders == []


def test_core_schema_source_imports_are_directional() -> None:
    forbidden_pairs = {
        "ergon_core.core.views.runs.models": (
            "EvalCriterionStatus = Literal",
            "GraphMutationValue =",
        ),
        "ergon_core.core.views.dashboard_events.contracts": (
            "GraphMutationValue =",
            "CancelCause = Literal",
        ),
    }

    offenders: list[str] = []
    for module_path, snippets in forbidden_pairs.items():
        path = ROOT / ("ergon_core/" + module_path.replace(".", "/") + ".py")
        text = path.read_text()
        for snippet in snippets:
            if snippet in text:
                offenders.append(f"{path.relative_to(ROOT)} contains local source {snippet!r}")

    assert offenders == []


def test_legacy_experiment_record_is_deleted() -> None:
    allowed_tests = {
        ROOT / "ergon_core/tests/unit/architecture/test_core_schema_sources.py",
    }
    offenders: list[str] = []

    for base in (
        ROOT / "ergon_core/ergon_core/core",
        ROOT / "ergon_cli/ergon_cli",
        ROOT / "ergon_core/tests/unit",
        ROOT / "ergon_cli/tests/unit",
    ):
        for path in base.rglob("*.py"):
            if path in allowed_tests or "__pycache__" in path.parts:
                continue
            if ("Benchmark" + "DefinitionRecord") in path.read_text():
                offenders.append(str(path.relative_to(ROOT)))

    assert offenders == []


def test_deprecated_cohort_tables_are_deleted() -> None:
    allowed_tests = {
        ROOT / "ergon_core/tests/unit/architecture/test_core_schema_sources.py",
    }
    snippets = (
        "Experiment" + "Cohort",
        "Experiment" + "CohortStats",
        "Experiment" + "CohortStatus",
    )
    offenders: list[str] = []

    for base in (
        ROOT / "ergon_core/ergon_core/core",
        ROOT / "ergon_core/tests/unit",
    ):
        for path in base.rglob("*.py"):
            if path in allowed_tests or "__pycache__" in path.parts:
                continue
            text = path.read_text()
            for snippet in snippets:
                if snippet in text:
                    offenders.append(f"{path.relative_to(ROOT)} references {snippet}")

    assert offenders == []


def test_deprecated_cohort_compat_modules_are_deleted() -> None:
    for removed_path in (
        ROOT / ("ergon_core/ergon_core/core/application/compat/co" + "horts.py"),
        ROOT / "ergon_core/ergon_core/core/application/compat/legacy_experiments.py",
        ROOT / ("ergon_core/ergon_core/core/application/read_models/co" + "horts.py"),
        ROOT / ("ergon_core/ergon_core/core/views/compat/co" + "horts.py"),
        ROOT / ("ergon_core/ergon_core/core/views/dashboard_events/co" + "horts.py"),
        ROOT / ("ergon_core/ergon_core/core/infrastructure/http/routes/co" + "horts.py"),
    ):
        assert not removed_path.exists()


def test_deprecated_cohort_metadata_behavior_is_deleted() -> None:
    snippets = (
        'parsed_metadata().get("cohort_id")',
        "parsed_metadata().get('cohort_id')",
        "cohort_id_from_metadata",
        "build_legacy_cohort_marker_metadata",
        "write_legacy_cohort_marker",
    )
    offenders: list[str] = []

    for path in (ROOT / "ergon_core/ergon_core/core").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text()
        for snippet in snippets:
            if snippet in text:
                offenders.append(f"{path.relative_to(ROOT)} contains {snippet}")

    assert offenders == []


def test_production_callers_do_not_use_deprecated_cohort_read_model_path() -> None:
    offenders: list[str] = []

    for base in (
        ROOT / "ergon_core/ergon_core/core",
        ROOT / "ergon_cli/ergon_cli",
    ):
        for path in base.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            if ("application.read_models.co" + "horts") in path.read_text():
                offenders.append(str(path.relative_to(ROOT)))

    assert offenders == []


def test_dashboard_event_contracts_live_under_views_not_infrastructure() -> None:
    core_root = ROOT / "ergon_core/ergon_core/core"

    assert (core_root / "views" / "dashboard_events" / "contracts.py").exists()
    assert not (core_root / "infrastructure" / "dashboard" / "event_contracts.py").exists()


def test_core_uses_hybrid_layout_roots_without_nominal_domain() -> None:
    core = ROOT / "ergon_core/ergon_core/core"

    expected_dirs = {
        "application",
        "infrastructure",
        "persistence",
        "rl",
        "shared",
        "views",
    }
    removed_dirs = {
        "runtime",
        "api",
        "definitions",
        "composition",
        "sandbox",
        "dashboard",
    }
    actual_dirs = {
        path.name for path in core.iterdir() if path.is_dir() and path.name != "__pycache__"
    }

    assert expected_dirs <= actual_dirs
    assert "domain" not in actual_dirs
    assert not (core / "domain").exists()
    assert actual_dirs.isdisjoint(removed_dirs)


def test_core_hybrid_layout_import_directions() -> None:
    forbidden_imports = {
        "persistence": (
            "ergon_core.core.application",
            "ergon_core.core.infrastructure",
            "ergon_core.core.infrastructure.http",
        ),
        "application": (
            "ergon_core.core.infrastructure.http",
            "ergon_core.core.infrastructure.inngest.handlers",
        ),
    }

    offenders: list[str] = []
    for root_name, snippets in forbidden_imports.items():
        root = ROOT / "ergon_core/ergon_core/core" / root_name
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            text = path.read_text()
            for snippet in snippets:
                if snippet in text:
                    offenders.append(f"{path.relative_to(ROOT)} imports {snippet}")

    assert offenders == []


def test_application_event_contracts_do_not_import_outer_layers() -> None:
    events_root = ROOT / "ergon_core/ergon_core/core/application/events"
    forbidden_imports = (
        "ergon_core.core.infrastructure",
        "ergon_core.core.persistence",
        "ergon_core.core.infrastructure.http",
    )

    offenders: list[str] = []
    for path in events_root.rglob("*.py"):
        text = path.read_text()
        for snippet in forbidden_imports:
            if snippet in text:
                offenders.append(f"{path.relative_to(ROOT)} imports {snippet}")

    assert offenders == []


def test_runtime_event_contract_references_do_not_return() -> None:
    checked_paths = [
        path
        for base in (
            ROOT / "ergon_core",
            ROOT / "ergon_cli",
            ROOT / "ergon_builtins",
            ROOT / "tests",
        )
        for path in base.rglob("*.py")
        if "__pycache__" not in path.parts and path != Path(__file__).resolve()
    ]
    checked_paths.extend(path for path in CONFIG_REFERENCE_FILES if path.exists())

    stale_references = (
        ".".join(("ergon_core", "core", "runtime", "events")),
        "/".join(("core", "runtime", "events")),
    )

    offenders: list[str] = []
    for path in checked_paths:
        text = path.read_text()
        for snippet in stale_references:
            if snippet in text:
                offenders.append(f"{path.relative_to(ROOT)} references {snippet!r}")

    assert offenders == []


def test_context_stream_has_single_discriminated_part_union() -> None:
    context_parts = ROOT / "ergon_core/ergon_core/core/shared/context_parts.py"
    event_payloads = ROOT / "ergon_core/ergon_core/core/persistence/context/event_payloads.py"

    context_parts_text = context_parts.read_text()

    assert "ContextPart = Annotated[" in context_parts_text
    assert "ContextEventType = Literal[" in context_parts_text
    assert not event_payloads.exists()
    old_generation_names = (
        "Generation" + "Turn",
        "ModelRequest" + "Part",
        "ModelResponse" + "Part",
    )
    old_payload_names = (
        "SystemPrompt" + "Payload",
        "AssistantText" + "Payload",
        "ToolCall" + "Payload",
    )

    for name in old_generation_names:
        assert name not in context_parts_text
    for name in old_payload_names:
        assert name not in context_parts_text


def test_context_contract_has_no_retired_imports_or_aliases() -> None:
    checked_roots = (
        ROOT / "ergon_core",
        ROOT / "ergon_cli",
        ROOT / "ergon_builtins",
        ROOT / "tests",
    )
    forbidden_snippets = (
        ".".join(("domain", "generation", "context_parts")),
        ".".join(("persistence", "context", "event_payloads")),
        "Worker" + "Yield",
        "Context" + "Event" + "Payload",
    )

    offenders: list[str] = []
    for root in checked_roots:
        for path in root.rglob("*.py"):
            if "__pycache__" in path.parts or path == Path(__file__).resolve():
                continue
            text = path.read_text()
            for snippet in forbidden_snippets:
                if snippet in text:
                    offenders.append(f"{path.relative_to(ROOT)} references {snippet!r}")

    assert offenders == []


def test_generation_provider_resolution_does_not_live_in_core() -> None:
    try:
        spec = importlib.util.find_spec("ergon_core.core.providers.generation")
    except ModuleNotFoundError:
        spec = None
    assert spec is None


def test_workflow_propagation_does_not_live_in_execution_package() -> None:
    execution_package = ".".join(("ergon_core", "core", "runtime", "execution"))
    try:
        package_spec = importlib.util.find_spec(execution_package)
    except ModuleNotFoundError:
        package_spec = None
    assert package_spec is None

    try:
        propagation_spec = importlib.util.find_spec(f"{execution_package}.propagation")
    except ModuleNotFoundError:
        propagation_spec = None
    assert propagation_spec is None


def test_graph_domain_modules_do_not_live_in_services_package() -> None:
    moved_modules = (
        "graph_dto",
        "graph_lookup",
        "graph_repository",
        "workflow_propagation_service",
    )
    for module in moved_modules:
        try:
            old_spec = importlib.util.find_spec(f"ergon_core.core.runtime.services.{module}")
        except ModuleNotFoundError:
            old_spec = None
        assert old_spec is None

    for module in (
        "models",
        "lookup",
        "repository",
        "propagation",
    ):
        assert importlib.util.find_spec(f"ergon_core.core.application.graph.{module}") is not None


def test_runtime_services_do_not_import_api_schema_modules() -> None:
    offenders: list[str] = []
    for path in (ROOT / "ergon_core/ergon_core/core/runtime").rglob("*.py"):
        text = path.read_text()
        if (
            "ergon_core.core.infrastructure.http.routes.schemas" in text
            or "ergon_core.core.infrastructure.http.routes.runs" in text
        ):
            offenders.append(str(path.relative_to(ROOT)))

    assert offenders == []


def test_definition_and_composition_services_do_not_live_in_runtime_services() -> None:
    old_modules = (
        "ergon_core.core.runtime.services.experiment_validation_service",
        "ergon_core.core.runtime.services.experiment_persistence_service",
        "ergon_core.core.runtime.services.experiment_definition_service",
        "ergon_core.core.runtime.services.experiment_schemas",
    )
    for module_name in old_modules:
        try:
            old_spec = importlib.util.find_spec(module_name)
        except ModuleNotFoundError:
            old_spec = None
        assert old_spec is None

    new_modules = (
        "ergon_core.core.application.experiments.definition_writer",
        "ergon_core.core.application.experiments.service",
        "ergon_core.core.application.experiments.models",
    )
    for module_name in new_modules:
        assert importlib.util.find_spec(module_name) is not None


def test_runtime_services_package_no_longer_contains_domain_modules() -> None:
    services_dir = ROOT / "ergon_core/ergon_core/core/runtime/services"
    remaining = sorted(
        path.name for path in services_dir.glob("*.py") if path.name != "__init__.py"
    )

    assert remaining == []


def test_runtime_errors_are_domain_local() -> None:
    old_errors_dir = ROOT / "ergon_core/ergon_core/core/runtime/errors"
    assert not old_errors_dir.exists()

    for module_name in (
        "ergon_core.core.application.graph.errors",
        "ergon_core.core.application.tasks.errors",
        "ergon_core.core.application.workflows.errors",
        "ergon_core.core.application.evaluation.errors",
        "ergon_core.core.views.errors",
        "ergon_core.core.infrastructure.inngest.errors",
    ):
        assert importlib.util.find_spec(module_name) is not None

    offenders: list[str] = []
    for path in (ROOT / "ergon_core/ergon_core").rglob("*.py"):
        text = path.read_text()
        if "ergon_core.core.runtime.errors" in text:
            offenders.append(str(path.relative_to(ROOT)))

    assert offenders == []


def test_runtime_domain_contract_files_use_consistent_names() -> None:
    runtime_dir = ROOT / "ergon_core/ergon_core/core/runtime"
    forbidden_suffixes = ("_dto.py", "_models.py", "_schemas.py")
    offenders = sorted(
        str(path.relative_to(ROOT))
        for path in runtime_dir.rglob("*.py")
        if path.name.endswith(forbidden_suffixes)
    )

    assert offenders == []


def test_task_latest_execution_selection_lives_in_task_repository() -> None:
    queries_path = ROOT / "ergon_core/ergon_core/core/persistence/queries.py"
    repository_path = ROOT / "ergon_core/ergon_core/core/application/tasks/repository.py"

    assert not queries_path.exists()
    assert "def latest_for_node" in repository_path.read_text()


def test_runtime_and_builtins_do_not_use_task_execution_query_bag_for_domain_reads() -> None:
    offenders: list[str] = []
    for base in (
        ROOT / "ergon_core/ergon_core/core/runtime",
        ROOT / "ergon_builtins/ergon_builtins",
    ):
        for path in base.rglob("*.py"):
            text = path.read_text()
            if (
                "queries.task_executions.list_children_of" in text
                or "queries.task_executions.get_task_payload" in text
                or "queries.definitions.get_task_with_instance" in text
            ):
                offenders.append(str(path.relative_to(ROOT)))

    assert offenders == []


def test_resource_viewer_limits_live_with_read_model_resources() -> None:
    api_path = ROOT / "ergon_core/ergon_core/core/infrastructure/http/routes/runs.py"
    resource_path = ROOT / "ergon_core/ergon_core/core/views/resources.py"

    assert "_RESOURCE_CONTENT_MAX_BYTES" not in api_path.read_text()
    assert "RESOURCE_CONTENT_MAX_BYTES" in resource_path.read_text()


def test_task_lifecycle_has_one_front_door_service() -> None:
    old_modules = (
        "ergon_core.core.application.tasks.cancellation",
        "ergon_core.core.application.tasks.blocking",
    )
    for module_name in old_modules:
        try:
            spec = importlib.util.find_spec(module_name)
        except ModuleNotFoundError:
            spec = None
        assert spec is None

    management = ROOT / "ergon_core/ergon_core/core/application/tasks/management.py"
    text = management.read_text()
    assert "def cancel_orphans(" in text
    assert "def block_pending_descendants(" in text


def test_deprecated_cohort_compatibility_has_one_front_door_service() -> None:
    old_module = "ergon_core.core.application.read_models.cohort_stats"
    try:
        spec = importlib.util.find_spec(old_module)
    except ModuleNotFoundError:
        spec = None
    assert spec is None

    removed_grouping_module = ROOT / (
        "ergon_core/ergon_core/core/application/compat/co" + "horts.py"
    )
    assert not removed_grouping_module.exists()


def test_workflow_lifecycle_has_one_front_door_service() -> None:
    old_modules = (
        "ergon_core.core.application.workflows.initialization",
        "ergon_core.core.application.workflows.finalization",
        "ergon_core.core.application.workflows.propagation",
    )
    for module_name in old_modules:
        try:
            spec = importlib.util.find_spec(module_name)
        except ModuleNotFoundError:
            spec = None
        assert spec is None

    workflow_service = ROOT / "ergon_core/ergon_core/core/application/workflows/service.py"
    text = workflow_service.read_text()
    for method_name in ("initialize", "propagate", "propagate_failure", "finalize"):
        assert f"def {method_name}(" in text


def test_evaluation_workflow_has_one_front_door_service() -> None:
    old_modules = (
        "ergon_core.core.application.evaluation.dispatch",
        "ergon_core.core.application.evaluation.rubric",
        "ergon_core.core.application.evaluation.persistence",
    )
    for module_name in old_modules:
        try:
            spec = importlib.util.find_spec(module_name)
        except ModuleNotFoundError:
            spec = None
        assert spec is None

    service = ROOT / "ergon_core/ergon_core/core/application/evaluation/service.py"
    text = service.read_text()
    for method_name in ("evaluate", "persist_success", "persist_failure"):
        assert f"def {method_name}(" in text


def test_persistence_layer_does_not_expose_domain_query_bag_or_runtime_context_service() -> None:
    assert not (ROOT / "ergon_core/ergon_core/core/persistence/queries.py").exists()
    assert not (ROOT / "ergon_core/ergon_core/core/persistence/context/repository.py").exists()

    offenders: list[str] = []
    checked_paths = [
        path
        for base in (
            ROOT / "ergon_core/ergon_core",
            ROOT / "ergon_builtins/ergon_builtins",
        )
        for path in base.rglob("*.py")
        if "__pycache__" not in path.parts and path != Path(__file__).resolve()
    ]
    checked_paths.extend(path for path in CONFIG_REFERENCE_FILES if path.exists())

    dotted_query = ".".join(("ergon_core", "core", "persistence", "queries"))
    dotted_context_repository = ".".join(
        ("ergon_core", "core", "persistence", "context", "repository")
    )
    path_query = "/".join(("ergon_core", "ergon_core", "core", "persistence", "queries.py"))
    suffix_query = "/".join(("persistence", "queries.py"))
    path_context_repository = "/".join(
        (
            "ergon_core",
            "ergon_core",
            "core",
            "persistence",
            "context",
            "repository.py",
        )
    )
    suffix_context_repository = "/".join(("persistence", "context", "repository.py"))

    for path in checked_paths:
        text = path.read_text()
        if dotted_query in text or path_query in text or suffix_query in text:
            offenders.append(str(path.relative_to(ROOT)))
        if (
            dotted_context_repository in text
            or path_context_repository in text
            or suffix_context_repository in text
        ):
            offenders.append(str(path.relative_to(ROOT)))

    assert offenders == []


def test_single_consumer_telemetry_repository_is_deleted() -> None:
    repository_path = ROOT / "ergon_core/ergon_core/core/persistence/telemetry/repository.py"

    assert not repository_path.exists()


def test_experiment_lifecycle_uses_module_level_functions() -> None:
    service_path = ROOT / "ergon_core/ergon_core/core/application/experiments/service.py"
    service_text = service_path.read_text()
    writer_path = ROOT / "ergon_core/ergon_core/core/application/experiments/definition_writer.py"
    writer_text = writer_path.read_text()

    # PR 6.5 cleanup: ExperimentService façade collapsed; persistence and
    # launch are module-level functions matching the Benchmark-direct shape.
    assert "async def run_experiment(" in service_text
    assert "def persist_benchmark(" in writer_text

    # define_benchmark_experiment, persist_definition, and the
    # ExperimentService class itself must all be gone.
    assert "def define_benchmark_experiment(" not in service_text
    assert "def persist_definition(" not in service_text
    assert "class ExperimentService" not in service_text

    forbidden_class_names = (
        "class ExperimentService",
        "class ExperimentDefinitionService",
        "class ExperimentPersistenceService",
        "class ExperimentLaunchService",
    )
    for path in (
        service_path,
        writer_path,
        ROOT / "ergon_core/ergon_core/core/application/experiments/launch.py",
    ):
        text = path.read_text()
        for class_name in forbidden_class_names:
            assert class_name not in text
