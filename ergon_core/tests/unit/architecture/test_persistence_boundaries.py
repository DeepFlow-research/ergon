"""Architecture guards for persistence boundaries."""

import importlib
from pathlib import Path

from sqlmodel import SQLModel

FORBIDDEN_PATTERNS = (
    "get_session(",
    "session.exec(",
    "session.get(",
    "select(",
)

ALLOWLIST = {
    # Test harness endpoints are explicitly debug/dev-only and expose raw state
    # for rollout inspection. They should remain isolated behind settings gates.
    Path("ergon_core/ergon_core/core/infrastructure/http/routes/test_harness.py"),
    # Context events are streamed from the application job as each model turn
    # lands; this older path is intentionally deferred until the context
    # event repository owns its transaction boundary.
    Path("ergon_core/ergon_core/core/jobs/task/worker_execute/job.py"),
    # Workflow lifecycle jobs still own small transactional updates.
    # New jobs should use repositories/services instead.
    Path("ergon_core/ergon_core/core/jobs/workflow/start/job.py"),
    Path("ergon_core/ergon_core/core/jobs/run/cleanup/job.py"),
    Path("ergon_core/ergon_core/core/jobs/task/cleanup_cancelled/job.py"),
    Path("ergon_core/ergon_core/core/jobs/task/cancel_orphans/job.py"),
    Path("ergon_core/ergon_core/core/jobs/workflow/complete/job.py"),
    Path("ergon_core/ergon_core/core/jobs/sandbox/setup/job.py"),
    Path("ergon_core/ergon_core/core/jobs/workflow/fail/job.py"),
    Path("ergon_core/ergon_core/core/jobs/resources/persist_outputs/job.py"),
    Path("ergon_core/ergon_core/core/jobs/task/evaluate/job.py"),
    Path("ergon_core/ergon_core/core/jobs/task/execute/job.py"),
}

CHECKED_ROOTS = (
    Path("ergon_core/ergon_core/core/infrastructure/http/routes"),
    Path("ergon_core/ergon_core/core/infrastructure/dashboard"),
    Path("ergon_core/ergon_core/core/jobs"),
)


def test_db_access_stays_out_of_api_dashboard_and_inngest_layers() -> None:
    offenders: list[str] = []
    for root in CHECKED_ROOTS:
        for path in root.rglob("*.py"):
            if path in ALLOWLIST:
                continue
            text = path.read_text()
            matches = [pattern for pattern in FORBIDDEN_PATTERNS if pattern in text]
            if matches:
                offenders.append(f"{path}: {', '.join(matches)}")

    assert offenders == []


def test_telemetry_models_do_not_import_application_evaluation_summary() -> None:
    text = Path("ergon_core/ergon_core/core/persistence/telemetry/models.py").read_text()

    assert "core.application.evaluation.summary" not in text


def test_telemetry_models_do_not_define_application_command_dtos() -> None:
    text = Path("ergon_core/ergon_core/core/persistence/telemetry/models.py").read_text()

    assert "class CreateTaskEvaluation" not in text


def test_persistence_foreign_keys_reference_existing_columns() -> None:
    for module_name in (
        "ergon_core.core.persistence.context.models",
        "ergon_core.core.persistence.definitions.models",
        "ergon_core.core.persistence.graph.models",
        "ergon_core.core.persistence.telemetry.models",
    ):
        importlib.import_module(module_name)

    missing_targets: list[str] = []
    for table in SQLModel.metadata.tables.values():
        for foreign_key in table.foreign_keys:
            target_table = SQLModel.metadata.tables.get(foreign_key.column.table.name)
            if target_table is None or foreign_key.column.name not in target_table.columns:
                missing_targets.append(
                    f"{table.name}.{foreign_key.parent.name} -> "
                    f"{foreign_key.column.table.name}.{foreign_key.column.name}"
                )

    assert missing_targets == []


def test_persistence_import_reducer_models_are_absent() -> None:
    imports_dir = Path("ergon_core/ergon_core/core") / "persistence" / "imports"

    assert not imports_dir.exists()


def test_run_record_uses_definition_id_as_single_runtime_definition_identity() -> None:
    from ergon_core.core.persistence.telemetry.models import RunRecord

    assert "definition_id" in RunRecord.model_fields
    assert ("workflow" + "_definition_id") not in RunRecord.model_fields


def test_run_record_does_not_expose_legacy_definition_group_identity() -> None:
    from ergon_core.core.persistence.telemetry.models import RunRecord

    assert ("experiment" + "_id") not in RunRecord.model_fields
