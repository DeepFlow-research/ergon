"""Architecture guards for the student-facing public API boundary."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]

REMOVED_PUBLIC_API_MODULES = (
    "ergon_core.api.generation",
    "ergon_core.api.json_types",
    "ergon_core.api.run_resource",
    "ergon_core.api.criterion_runtime",
    "ergon_core.api.dependencies",
    "ergon_core.api.types",
)

FORBIDDEN_IMPORT_SNIPPETS = (
    "from ergon_core.api.generation import",
    "from ergon_core.api.json_types import",
    "from ergon_core.api.run_resource import",
    "from ergon_core.api.criterion_runtime import",
    "from ergon_core.api.dependencies import",
    "from ergon_core.api.types import",
)

CHECKED_ROOTS = (
    ROOT / "ergon_builtins",
    ROOT / "ergon_cli",
    ROOT / "ergon_core" / "ergon_core" / "core",
)

PYTHON_DOMAIN_ROOTS = (
    ROOT / "ergon_builtins" / "ergon_builtins",
    ROOT / "ergon_cli" / "ergon_cli",
    ROOT / "ergon_core" / "ergon_core",
    ROOT / "ergon_infra" / "ergon_infra",
)

EXPORT_FACADE_BOUNDARY_ROOTS = (
    ROOT / "ergon_core" / "ergon_core" / "api",
    ROOT / "ergon_core" / "ergon_core" / "core" / "shared",
)

INTERNAL_API_REFERENCE_ROOTS = (
    ROOT / "ergon_core",
    ROOT / "ergon_cli",
    ROOT / "ergon_builtins",
    ROOT / "tests",
)

INTERNAL_API_REFERENCE_FILES = (
    ROOT / "pyproject.toml",
    ROOT / "Dockerfile",
    ROOT / "docker-compose.yml",
)

STALE_INTERNAL_API_SNIPPETS = (
    "ergon_core.core.api",
    "ergon_core/ergon_core/core/api",
)

OLD_CORE_DOMAIN_IMPORT_SNIPPETS = (
    "ergon_core.core.composition",
    "ergon_core.core.generation",
    "ergon_core.core.json_types",
    "ergon_core.core.settings",
    "ergon_core.core.utils",
)

OLD_EXPERIMENT_APPLICATION_REFERENCE_SNIPPETS = (
    ".".join(("ergon_core", "core", "definitions")),
    ".".join(("ergon_core", "core", "runtime", "workflows", "launch")),
    "/".join(("ergon_core", "ergon_core", "core", "definitions")),
    "/".join(
        (
            "ergon_core",
            "ergon_core",
            "core",
            "runtime",
            "workflows",
            "launch.py",
        )
    ),
)

OLD_APPLICATION_RUNTIME_REFERENCE_SNIPPETS = (
    ".".join(("ergon_core", "core", "runtime", "execution")),
    ".".join(("ergon_core", "core", "runtime", "workflows")),
    ".".join(("ergon_core", "core", "runtime", "graph")),
    ".".join(("ergon_core", "core", "runtime", "tasks")),
    ".".join(("ergon_core", "core", "runtime", "evaluation")),
    "/".join(("ergon_core", "ergon_core", "core", "runtime", "execution")),
    "/".join(("ergon_core", "ergon_core", "core", "runtime", "workflows")),
    "/".join(("ergon_core", "ergon_core", "core", "runtime", "graph")),
    "/".join(("ergon_core", "ergon_core", "core", "runtime", "tasks")),
    "/".join(("ergon_core", "ergon_core", "core", "runtime", "evaluation")),
)

OLD_RUNTIME_READ_CONTEXT_RESOURCE_REFERENCE_SNIPPETS = (
    ".".join(("ergon_core", "core", "runtime", "read_models")),
    ".".join(("ergon_core", "core", "runtime", "context_events")),
    ".".join(("ergon_core", "core", "runtime", "output_extraction")),
    ".".join(("ergon_core", "core", "runtime", "resources")),
    "/".join(("ergon_core", "ergon_core", "core", "runtime", "read_models")),
    "/".join(("ergon_core", "ergon_core", "core", "runtime", "context_events")),
    "/".join(("ergon_core", "ergon_core", "core", "runtime", "output_extraction")),
    "/".join(("ergon_core", "ergon_core", "core", "runtime", "resources")),
)

OLD_RUNTIME_INNGEST_REFERENCE_SNIPPETS = (
    ".".join(("ergon_core", "core", "runtime", "inngest")),
    "/".join(("ergon_core", "ergon_core", "core", "runtime", "inngest")),
)

OLD_INFRASTRUCTURE_REFERENCE_SNIPPETS = (
    ".".join(("ergon_core", "core", "sandbox")),
    ".".join(("ergon_core", "core", "dashboard")),
    ".".join(("ergon_core", "core", "runtime", "tracing")),
    ".".join(("ergon_core", "core", "runtime", "dependencies")),
    "/".join(("ergon_core", "ergon_core", "core", "sandbox")),
    "/".join(("ergon_core", "ergon_core", "core", "dashboard")),
    "/".join(("ergon_core", "ergon_core", "core", "runtime", "tracing")),
    "/".join(("ergon_core", "ergon_core", "core", "runtime", "dependencies.py")),
)


def test_runtime_and_builtin_code_do_not_import_core_types_through_public_api() -> None:
    offenders: list[str] = []
    for root in CHECKED_ROOTS:
        for path in root.rglob("*.py"):
            text = path.read_text()
            for snippet in FORBIDDEN_IMPORT_SNIPPETS:
                if snippet in text:
                    offenders.append(f"{path.relative_to(ROOT)} imports via {snippet!r}")

    assert offenders == []


def test_deleted_public_api_facade_modules_stay_deleted() -> None:
    restored = [
        module_name
        for module_name in REMOVED_PUBLIC_API_MODULES
        if importlib.util.find_spec(module_name) is not None
    ]

    assert restored == []


def test_internal_http_api_lives_under_infrastructure_http_not_core_api() -> None:
    core_root = ROOT / "ergon_core" / "ergon_core" / "core"

    assert not (core_root / "api").exists()
    assert not (core_root / "rest_api").exists()
    assert (core_root / "infrastructure" / "http").exists()


def test_code_and_config_do_not_reference_old_internal_core_api() -> None:
    checked_paths = [
        path
        for root in INTERNAL_API_REFERENCE_ROOTS
        for path in root.rglob("*.py")
        if "__pycache__" not in path.parts and path != Path(__file__).resolve()
    ]
    checked_paths.extend(path for path in INTERNAL_API_REFERENCE_FILES if path.exists())

    offenders: list[str] = []
    for path in checked_paths:
        text = path.read_text()
        for snippet in STALE_INTERNAL_API_SNIPPETS:
            if snippet in text:
                offenders.append(f"{path.relative_to(ROOT)} references {snippet!r}")

    assert offenders == []


def test_shared_and_domain_primitives_stay_in_new_core_layout() -> None:
    core_root = ROOT / "ergon_core" / "ergon_core" / "core"

    for old_path in (
        core_root / "composition",
        core_root / "generation.py",
        core_root / "json_types.py",
        core_root / "settings.py",
        core_root / "utils.py",
    ):
        assert not old_path.exists()

    for new_path in (
        core_root / "shared" / "context_parts.py",
        core_root / "shared" / "json_types.py",
        core_root / "shared" / "settings.py",
        core_root / "shared" / "utils.py",
    ):
        assert new_path.exists()

    assert not (core_root / "domain").exists()


def test_code_does_not_import_old_core_domain_paths() -> None:
    offenders: list[str] = []
    checked_paths = [
        path
        for domain_root in PYTHON_DOMAIN_ROOTS
        for path in domain_root.rglob("*.py")
        if "__pycache__" not in path.parts and path != Path(__file__).resolve()
    ]
    checked_paths.extend(
        path
        for root in (ROOT / "tests",)
        for path in root.rglob("*.py")
        if "__pycache__" not in path.parts and path != Path(__file__).resolve()
    )

    for path in checked_paths:
        text = path.read_text()
        for snippet in OLD_CORE_DOMAIN_IMPORT_SNIPPETS:
            if snippet in text:
                offenders.append(f"{path.relative_to(ROOT)} references {snippet!r}")

    assert offenders == []


def test_experiment_application_cluster_stays_in_new_core_layout() -> None:
    core_root = ROOT / "ergon_core" / "ergon_core" / "core"

    assert not (core_root / "definitions").exists()
    assert not (core_root / "runtime" / "workflows" / "launch.py").exists()
    for new_path in (
        core_root / "application" / "experiments" / "__init__.py",
        core_root / "application" / "experiments" / "service.py",
        core_root / "application" / "experiments" / "models.py",
        core_root / "application" / "experiments" / "definition_writer.py",
        core_root / "application" / "experiments" / "launch.py",
    ):
        assert new_path.exists()

    offenders: list[str] = []
    checked_paths = [
        path
        for root in INTERNAL_API_REFERENCE_ROOTS
        for path in root.rglob("*.py")
        if "__pycache__" not in path.parts and path != Path(__file__).resolve()
    ]
    checked_paths.extend(path for path in INTERNAL_API_REFERENCE_FILES if path.exists())
    for path in checked_paths:
        text = path.read_text()
        for snippet in OLD_EXPERIMENT_APPLICATION_REFERENCE_SNIPPETS:
            if snippet in text:
                offenders.append(f"{path.relative_to(ROOT)} references {snippet!r}")

    assert offenders == []


def test_application_clusters_stay_out_of_runtime_layout() -> None:
    core_root = ROOT / "ergon_core" / "ergon_core" / "core"

    for old_dir in (
        core_root / "runtime" / "execution",
        core_root / "runtime" / "workflows",
        core_root / "runtime" / "graph",
        core_root / "runtime" / "tasks",
        core_root / "runtime" / "evaluation",
    ):
        assert not old_dir.exists()

    for retired_path in (
        core_root / "application" / "workflows",
        core_root / "application" / "graph",
        core_root / "application" / "tasks",
    ):
        assert not retired_path.exists()

    for new_path in (
        core_root / "application" / "runtime" / "__init__.py",
        core_root / "application" / "runtime" / "sample_lifecycle.py",
        core_root / "application" / "runtime" / "orchestration.py",
        core_root / "application" / "runtime" / "sample_records.py",
        core_root / "application" / "runtime" / "workflow_models.py",
        core_root / "application" / "runtime" / "graph_repository.py",
        core_root / "application" / "runtime" / "lifecycle.py",
        core_root / "application" / "runtime" / "graph_traversal.py",
        core_root / "application" / "runtime" / "graph_lookup.py",
        core_root / "application" / "runtime" / "models.py",
        core_root / "application" / "runtime" / "errors.py",
        core_root / "application" / "runtime" / "task_service.py",
        core_root / "application" / "runtime" / "task_execution.py",
        core_root / "application" / "runtime" / "task_management.py",
        core_root / "application" / "runtime" / "task_inspection.py",
        core_root / "application" / "runtime" / "task_cleanup.py",
        core_root / "application" / "runtime" / "task_execution_repository.py",
        core_root / "application" / "runtime" / "task_models.py",
        core_root / "application" / "runtime" / "task_errors.py",
        core_root / "application" / "evaluation" / "__init__.py",
        core_root / "application" / "evaluation" / "service.py",
        core_root / "application" / "evaluation" / "scoring.py",
        core_root / "application" / "evaluation" / "models.py",
        core_root / "application" / "evaluation" / "errors.py",
    ):
        assert new_path.exists()

    offenders: list[str] = []
    checked_paths = [
        path
        for root in INTERNAL_API_REFERENCE_ROOTS
        for path in root.rglob("*.py")
        if "__pycache__" not in path.parts and path != Path(__file__).resolve()
    ]
    checked_paths.extend(path for path in INTERNAL_API_REFERENCE_FILES if path.exists())
    for path in checked_paths:
        text = path.read_text()
        for snippet in OLD_APPLICATION_RUNTIME_REFERENCE_SNIPPETS:
            if snippet in text:
                offenders.append(f"{path.relative_to(ROOT)} references {snippet!r}")

    assert offenders == []


def test_read_context_and_resource_modules_stay_in_application_and_views_layout() -> None:
    core_root = ROOT / "ergon_core" / "ergon_core" / "core"

    for old_path in (
        core_root / "runtime" / "read_models",
        core_root / "runtime" / "context_events.py",
        core_root / "runtime" / "output_extraction.py",
        core_root / "runtime" / "resources.py",
        core_root / "application" / "read_models",
        core_root / "application" / "read_models" / "models.py",
        core_root / "application" / "read_models" / "samples.py",
        core_root / "application" / "read_models" / "run_snapshot.py",
        core_root / "application" / "read_models" / "experiments.py",
        core_root / "application" / "read_models" / "resources.py",
        core_root / "application" / "read_models" / "errors.py",
        core_root / "application" / "read_models" / ("co" + "horts.py"),
    ):
        assert not old_path.exists()

    for new_path in (
        core_root / "application" / "communication" / "__init__.py",
        core_root / "application" / "communication" / "service.py",
        core_root / "application" / "communication" / "models.py",
        core_root / "application" / "communication" / "errors.py",
        core_root / "application" / "context" / "__init__.py",
        core_root / "application" / "context" / "service.py",
        core_root / "application" / "resources" / "__init__.py",
        core_root / "application" / "resources" / "models.py",
        core_root / "application" / "resources" / "repository.py",
        core_root / "views" / "__init__.py",
        core_root / "views" / "samples" / "__init__.py",
        core_root / "views" / "samples" / "models.py",
        core_root / "views" / "samples" / "service.py",
        core_root / "views" / "samples" / "snapshot.py",
        core_root / "views" / "experiments" / "__init__.py",
        core_root / "views" / "experiments" / "models.py",
        core_root / "views" / "experiments" / "service.py",
        core_root / "views" / "resources.py",
        core_root / "views" / "errors.py",
    ):
        assert new_path.exists()

    checked_paths = [
        path
        for root in INTERNAL_API_REFERENCE_ROOTS
        for path in root.rglob("*.py")
        if "__pycache__" not in path.parts and path != Path(__file__).resolve()
    ]
    checked_paths.extend(path for path in INTERNAL_API_REFERENCE_FILES if path.exists())

    offenders: list[str] = []
    for path in checked_paths:
        text = path.read_text()
        for snippet in OLD_RUNTIME_READ_CONTEXT_RESOURCE_REFERENCE_SNIPPETS:
            if snippet in text:
                offenders.append(f"{path.relative_to(ROOT)} references {snippet!r}")

    assert offenders == []


def test_views_package_replaces_non_compat_read_models() -> None:
    core_root = ROOT / "ergon_core" / "ergon_core" / "core"
    read_models_root = core_root / "application" / "read_models"
    views_root = core_root / "views"

    for removed_path in (
        read_models_root / "models.py",
        read_models_root / "samples.py",
        read_models_root / "run_snapshot.py",
        read_models_root / "experiments.py",
        read_models_root / "resources.py",
        read_models_root / "errors.py",
        read_models_root / ("co" + "horts.py"),
    ):
        assert not removed_path.exists()

    for new_path in (
        views_root / "__init__.py",
        views_root / "samples" / "__init__.py",
        views_root / "samples" / "models.py",
        views_root / "samples" / "service.py",
        views_root / "samples" / "snapshot.py",
        views_root / "experiments" / "__init__.py",
        views_root / "experiments" / "models.py",
        views_root / "experiments" / "service.py",
        views_root / "resources.py",
        views_root / "errors.py",
    ):
        assert new_path.exists()


def test_views_modules_stay_read_only_and_adapter_free() -> None:
    views_root = ROOT / "ergon_core" / "ergon_core" / "core" / "views"

    offenders: list[str] = []
    forbidden_snippets = (
        "session.add(",
        "session.commit(",
        "ergon_core.core.infrastructure",
        ".".join(("ergon_core", "core", "application", "jobs")),
        "start_workflow",
    )

    assert views_root.exists()
    for path in views_root.rglob("*.py"):
        text = path.read_text()
        for snippet in forbidden_snippets:
            if snippet in text:
                offenders.append(f"{path.relative_to(ROOT)} contains {snippet!r}")

    assert offenders == []


def test_views_services_may_read_persistence_rows() -> None:
    views_root = ROOT / "ergon_core" / "ergon_core" / "core" / "views"

    for path in (
        views_root / "samples" / "service.py",
        views_root / "experiments" / "service.py",
    ):
        text = path.read_text()
        assert "get_session" in text
        assert "select(" in text


def _inngest_job_boundary_offenders(core_root: Path) -> list[str]:
    """PR 10 keeps decorators in job-local adapters, not in job bodies."""

    # Runtime symbols on the `inngest` package whose use inside a job
    # would re-introduce the coupling we're trying to keep in handlers.
    # `inngest.Context` and `inngest.Function` are explicitly allowed
    # (they're types, used only in annotations).
    forbidden_runtime_inngest_symbols = (
        "inngest.NonRetriableError",
        "inngest.RetryAfterError",
        "inngest.TriggerEvent",
        "inngest.TriggerCron",
        "inngest.Inngest",
        "inngest.create_function",
    )

    offenders: list[str] = []
    for path in (core_root / "jobs").rglob("job.py"):
        text = path.read_text()
        lines = text.splitlines()
        if any(line.startswith("from inngest ") for line in lines):
            offenders.append(
                f"{path.relative_to(ROOT)} uses `from inngest import ...`; "
                "type annotations should reference `inngest.Context` / `inngest.Function` via the module-level import"
            )
        for symbol in forbidden_runtime_inngest_symbols:
            if symbol in text:
                offenders.append(
                    f"{path.relative_to(ROOT)} uses runtime symbol {symbol!r}; "
                    "this belongs in the infrastructure handler layer"
                )
        if "@inngest_client.create_function" in text:
            offenders.append(f"{path.relative_to(ROOT)} owns an Inngest decorator")
        offenders.extend(
            f"{path.relative_to(ROOT)} has unsupported Inngest infrastructure import: {line}"
            for line in lines
            if "ergon_core.core.infrastructure.inngest." in line
            and "client import" not in line
            and "errors import" not in line
        )

    return offenders


def test_inngest_jobs_use_job_local_adapters() -> None:
    core_root = ROOT / "ergon_core" / "ergon_core" / "core"

    assert not (core_root / "runtime" / "inngest").exists()

    for new_path in (
        core_root / "infrastructure" / "inngest" / "__init__.py",
        core_root / "infrastructure" / "inngest" / "client.py",
        core_root / "infrastructure" / "inngest" / "registry.py",
        core_root / "infrastructure" / "inngest" / "errors.py",
        core_root / "jobs" / "__init__.py",
    ):
        assert new_path.exists()

    assert not (core_root / "application" / "jobs").exists()
    assert not (core_root / "infrastructure" / "inngest" / "handlers").exists()
    assert not (core_root / "infrastructure" / "inngest" / "contracts.py").exists()

    offenders = _inngest_job_boundary_offenders(core_root)

    registry_text = (core_root / "infrastructure" / "inngest" / "registry.py").read_text()
    assert "ergon_core.core.jobs" in registry_text

    checked_paths = [
        path
        for root in INTERNAL_API_REFERENCE_ROOTS
        for path in root.rglob("*.py")
        if "__pycache__" not in path.parts and path != Path(__file__).resolve()
    ]
    for path in checked_paths:
        text = path.read_text()
        for snippet in OLD_RUNTIME_INNGEST_REFERENCE_SNIPPETS:
            if snippet in text:
                offenders.append(f"{path.relative_to(ROOT)} references {snippet!r}")

    assert offenders == []


def test_sandbox_dashboard_tracing_and_dependencies_stay_in_infrastructure() -> None:
    core_root = ROOT / "ergon_core" / "ergon_core" / "core"

    for old_path in (
        core_root / "sandbox",
        core_root / "dashboard",
        core_root / "runtime" / "tracing",
        core_root / "runtime" / "dependencies.py",
    ):
        assert not old_path.exists()

    for new_path in (
        core_root / "infrastructure" / "sandbox" / "__init__.py",
        core_root / "infrastructure" / "sandbox" / "manager.py",
        core_root / "infrastructure" / "sandbox" / "lifecycle.py",
        core_root / "infrastructure" / "sandbox" / "resource_publisher.py",
        core_root / "infrastructure" / "sandbox" / "instrumentation.py",
        core_root / "infrastructure" / "sandbox" / "event_sink.py",
        core_root / "infrastructure" / "sandbox" / "errors.py",
        core_root / "infrastructure" / "sandbox" / "utils.py",
        core_root / "infrastructure" / "dashboard" / "__init__.py",
        core_root / "infrastructure" / "dashboard" / "emitter.py",
        core_root / "infrastructure" / "dashboard" / "provider.py",
        core_root / "views" / "dashboard_events" / "contracts.py",
        core_root / "views" / "dashboard_events" / "graph_mutations.py",
        core_root / "views" / "dashboard_events" / "context_events.py",
        core_root / "infrastructure" / "tracing" / "__init__.py",
        core_root / "infrastructure" / "tracing" / "attributes.py",
        core_root / "infrastructure" / "tracing" / "contexts.py",
        core_root / "infrastructure" / "tracing" / "ids.py",
        core_root / "infrastructure" / "tracing" / "noop.py",
        core_root / "infrastructure" / "tracing" / "otel.py",
        core_root / "infrastructure" / "tracing" / "sinks.py",
        core_root / "infrastructure" / "tracing" / "types.py",
        core_root / "infrastructure" / "dependencies.py",
    ):
        assert new_path.exists()

    checked_paths = [
        path
        for root in (*INTERNAL_API_REFERENCE_ROOTS, ROOT / "scripts")
        for path in root.rglob("*.py")
        if "__pycache__" not in path.parts and path != Path(__file__).resolve()
    ]
    checked_paths.extend(path for path in INTERNAL_API_REFERENCE_FILES if path.exists())

    offenders: list[str] = []
    for path in checked_paths:
        text = path.read_text()
        for snippet in OLD_INFRASTRUCTURE_REFERENCE_SNIPPETS:
            if snippet in text:
                offenders.append(f"{path.relative_to(ROOT)} references {snippet!r}")

    assert offenders == []


def test_python_domain_leaf_modules_do_not_define_export_facades() -> None:
    offenders = [
        path.relative_to(ROOT)
        for boundary_root in EXPORT_FACADE_BOUNDARY_ROOTS
        for path in boundary_root.rglob("*.py")
        if path.name != "__init__.py" and "__all__" in path.read_text()
    ]

    assert offenders == []


def test_e2e_tests_do_not_import_private_core_repositories() -> None:
    e2e_dir = ROOT / "tests" / "e2e"
    forbidden = (
        "ergon_core.core.persistence.",
        "ergon_core.core.runtime.tasks.repository",
        "ergon_core.core.runtime.evaluation.persistence",
        "ergon_core.core.runtime.inngest.",
    )

    offenders: list[str] = []
    for path in e2e_dir.rglob("*.py"):
        text = path.read_text()
        for needle in forbidden:
            if needle in text:
                offenders.append(f"{path.relative_to(ROOT)} imports {needle!r}")

    assert offenders == []


def test_local_api_composition_mounts_test_owned_smoke_components() -> None:
    api_app = ROOT / "ergon_cli" / "ergon_cli" / "api_app.py"
    compose = ROOT / "docker-compose.yml"

    assert "ergon_core.core.infrastructure.http.app" in api_app.read_text()
    assert "tests.fixtures.smoke_components" not in api_app.read_text()
    assert "./tests:/app/tests" in compose.read_text()
