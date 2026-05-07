import json
from pathlib import Path

import pyarrow.parquet as pq
import pytest
from sqlmodel import SQLModel, Session, create_engine

from ergon_ingestion.exports.models import ShardedExportConfig
from ergon_ingestion.exports.sharded import export_dataset
from ergon_ingestion.exports.verify import verify_export
from ergon_ingestion.models import ImportSource, ParsedDrop, ParsedReducer, ParsedResource, ParsedRun
from ergon_ingestion.writers.external_run_writer import ExternalRunWriter


def test_sharded_export_writes_parquet_manifest_state_and_resources(tmp_path: Path) -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _write_imported_runs(session=session, tmp_path=tmp_path, count=3)

        result = export_dataset(
            session=session,
            config=ShardedExportConfig(
                dataset="gap",
                batch="paper-gap-e2e-v1",
                output_dir=tmp_path / "export",
                shard_size_mb=0.001,
                page_size=2,
                resume=False,
            ),
        )

    manifest = json.loads((tmp_path / "export" / "manifest.json").read_text())
    state = json.loads((tmp_path / "export" / "state.json").read_text())
    assert result.run_count == 3
    assert manifest["run_count"] == 3
    assert manifest["reducer_count"] == 3
    assert manifest["drop_count"] == 3
    assert manifest["resource_count"] == 3
    assert state["phase"] == "completed"
    assert len(manifest["shards"]["runs"]) >= 2

    run_shard = tmp_path / "export" / manifest["shards"]["runs"][0]["path"]
    run_rows = pq.read_table(run_shard).to_pylist()
    assert set(run_rows[0]) >= {
        "dataset",
        "batch",
        "run_id",
        "sample_id",
        "instance_key",
        "observed_fields_json",
        "resources_json",
    }
    resources = json.loads(run_rows[0]["resources_json"])
    assert resources[0]["export_path"].startswith("resources/")
    assert (tmp_path / "export" / resources[0]["export_path"]).exists()

    verification = verify_export(tmp_path / "export")
    assert verification["ok"] is True
    assert verification["run_count"] == 3


def test_verify_export_rejects_resource_hash_mismatch(tmp_path: Path) -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _write_imported_runs(session=session, tmp_path=tmp_path, count=1)
        export_dataset(
            session=session,
            config=ShardedExportConfig(
                dataset="gap",
                batch="paper-gap-e2e-v1",
                output_dir=tmp_path / "export",
            ),
        )

    resource = next((tmp_path / "export" / "resources").rglob("*.json"))
    data = bytearray(resource.read_bytes())
    data[0] = ord("x") if data[0] != ord("x") else ord("y")
    resource.write_bytes(data)

    with pytest.raises(RuntimeError, match="resource_hash_mismatch"):
        verify_export(tmp_path / "export")


def test_sharded_export_resume_reuses_verified_completed_export(tmp_path: Path) -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _write_imported_runs(session=session, tmp_path=tmp_path, count=1)
        config = ShardedExportConfig(
            dataset="gap",
            batch="paper-gap-e2e-v1",
            output_dir=tmp_path / "export",
            resume=True,
        )
        first = export_dataset(session=session, config=config)
        _write_imported_runs(session=session, tmp_path=tmp_path, count=1)
        second = export_dataset(session=session, config=config)

    assert second.run_count == first.run_count


def _write_imported_runs(*, session: Session, tmp_path: Path, count: int) -> None:
    writer = ExternalRunWriter(
        session=session,
        source=ImportSource(dataset="gap", input_path=tmp_path, batch_id="paper-gap-e2e-v1"),
        blob_root=tmp_path / "blobs",
    )
    for index in range(count):
        writer.write_run(
            ParsedRun(
                source_run_id=f"gap-row-{index}",
                instance_key=f"gap-row-{index}",
                description=f"Imported GAP row {index}",
                schema_fit_class="row-record",
                observed_fields={"row": index, "safe": index % 2 == 0},
                missing_fields=["full_runtime_environment"],
                resources=[
                    ParsedResource(
                        name="source-row.json",
                        kind="import",
                        mime_type="application/json",
                        payload={"row": index, "trace": ["step", index]},
                    )
                ],
                reducers=[
                    ParsedReducer(
                        name="gap.text_safety",
                        kind="original",
                        output={"safe": index % 2 == 0},
                        implementation_ref="ergon_ingestion.reducers.gap:text_safety",
                        fields_read=["safe"],
                        drops=[
                            ParsedDrop(
                                loss_class="unavailable_source_field",
                                reason="missing_runtime",
                                dropped_field_path="runtime",
                                affected_analysis="gap.text_safety",
                            )
                        ],
                    )
                ],
            )
        )
    session.commit()
