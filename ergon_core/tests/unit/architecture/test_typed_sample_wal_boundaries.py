from pathlib import Path

from sqlmodel import SQLModel


ROOT = Path(__file__).resolve().parents[4]
CORE_ROOT = ROOT / "ergon_core" / "ergon_core"


def test_typed_sample_wal_uses_separate_tables_without_component_interner() -> None:
    import ergon_core.core.persistence.samples.models  # noqa: F401

    expected_tables = {
        "sample_status_events",
        "sample_task_events",
        "sample_edge_events",
        "sample_worker_events",
        "sample_evaluator_events",
        "sample_sandbox_events",
        "sample_annotation_events",
    }

    assert expected_tables.issubset(SQLModel.metadata.tables)
    assert "sample_events" not in SQLModel.metadata.tables
    assert "sample_component_interners" not in SQLModel.metadata.tables
    assert "sample_runtime_components" not in SQLModel.metadata.tables


def test_sample_application_dtos_do_not_import_dashboard_or_http_layers() -> None:
    samples_app_root = CORE_ROOT / "core" / "application" / "samples"

    offenders: list[str] = []
    for path in samples_app_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for forbidden in (
            "core.views.dashboard_events",
            "core.infrastructure.http",
            "core.views.samples",
        ):
            if forbidden in text:
                offenders.append(f"{path.relative_to(ROOT)} imports {forbidden}")

    assert offenders == []
