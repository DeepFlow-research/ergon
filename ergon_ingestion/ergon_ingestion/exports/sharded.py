"""Sharded Ergon export implementation."""

import hashlib
import json
import shutil
from pathlib import Path
from typing import Iterable
from uuid import UUID

import pyarrow as pa
import pyarrow.parquet as pq
from sqlmodel import Session, select

from ergon_core.core.persistence.imports.models import RunDropsManifest, RunReducer
from ergon_core.core.persistence.telemetry.models import ExperimentRecord, RunRecord, RunResource
from ergon_ingestion.exports.models import (
    DatasetExportManifest,
    ExportState,
    ShardRecord,
    ShardedExportConfig,
    dump_model_json,
)


def export_dataset(*, session: Session, config: ShardedExportConfig) -> DatasetExportManifest:
    """Export one imported dataset as sharded Ergon-native files."""

    if config.format != "parquet":
        raise ValueError("only parquet export is currently supported")
    output_dir = config.output_dir
    manifest_path = output_dir / "manifest.json"
    if config.resume and manifest_path.exists():
        from ergon_ingestion.exports.verify import verify_export

        existing_export_valid = False
        try:
            verify_export(output_dir)
        except RuntimeError:
            existing_export_valid = False
        else:
            existing_export_valid = True

        if existing_export_valid:
            return DatasetExportManifest.model_validate(json.loads(manifest_path.read_text()))
    output_dir.mkdir(parents=True, exist_ok=True)
    for family in ("runs", "reducers", "drops", "resources"):
        (output_dir / family).mkdir(parents=True, exist_ok=True)

    state = ExportState(dataset=config.dataset, batch=config.batch)
    _write_text(output_dir / "state.json", dump_model_json(state))

    runs = _load_runs(session=session, dataset=config.dataset, batch=config.batch)
    checksums: dict[str, str] = {}
    resource_descriptors: dict[UUID, list[dict[str, object]]] = {}
    resource_count = 0
    resource_total_bytes = 0

    for run in runs:
        descriptors, copied_bytes = _export_resources(session, output_dir, run.id, config)
        resource_descriptors[run.id] = descriptors
        resource_count += len(descriptors)
        resource_total_bytes += copied_bytes

    run_rows = [_run_row(config, run, resource_descriptors.get(run.id, [])) for run in runs]
    reducer_rows = _load_reducer_rows(session=session, config=config, runs=runs)
    drop_rows = _load_drop_rows(session=session, config=config, runs=runs)

    shards = {
        "runs": _write_shards(output_dir, "runs", run_rows, config, checksums),
        "reducers": _write_shards(output_dir, "reducers", reducer_rows, config, checksums),
        "drops": _write_shards(output_dir, "drops", drop_rows, config, checksums),
    }
    state = ExportState(
        phase="completed",
        dataset=config.dataset,
        batch=config.batch,
        next_run_offset=len(runs),
        completed_shards=[record.path for family in shards.values() for record in family],
        last_run_id=str(runs[-1].id) if runs else None,
    )
    manifest = DatasetExportManifest(
        dataset=config.dataset,
        batch=config.batch,
        source_url=config.source_url,
        source_version_ref=config.source_version_ref,
        run_count=len(run_rows),
        reducer_count=len(reducer_rows),
        drop_count=len(drop_rows),
        resource_count=resource_count,
        resource_total_bytes=resource_total_bytes,
        shards=shards,
        malformed_source_records=_malformed_source_records(runs),
        verification={
            "ok": True,
            "resource_hashes_checked": resource_count,
            "shard_count": sum(len(records) for records in shards.values()),
        },
    )
    _write_text(output_dir / "state.json", dump_model_json(state))
    _write_text(output_dir / "manifest.json", dump_model_json(manifest))
    _write_text(
        output_dir / "checksums.json", json.dumps(checksums, indent=2, sort_keys=True) + "\n"
    )
    return manifest


def export_dataset_from_config(config: ShardedExportConfig) -> DatasetExportManifest:
    """Open the configured Ergon database session and export one dataset."""

    from ergon_core.core.persistence.shared.db import ensure_db, get_session

    ensure_db()
    with get_session() as session:
        return export_dataset(session=session, config=config)


def _load_runs(*, session: Session, dataset: str, batch: str) -> list[RunRecord]:
    statement = (
        select(RunRecord)
        .join(ExperimentRecord)
        .where(RunRecord.benchmark_type == f"imported:{dataset}")
        .where(ExperimentRecord.name == batch)
        .order_by(RunRecord.created_at, RunRecord.id)
    )
    return list(session.exec(statement))


def _export_resources(
    session: Session, output_dir: Path, run_id: UUID, config: ShardedExportConfig
) -> tuple[list[dict[str, object]], int]:
    resources = list(session.exec(select(RunResource).where(RunResource.run_id == run_id)))
    descriptors: list[dict[str, object]] = []
    copied_bytes = 0
    for resource in resources:
        if resource.content_hash is None:
            raise RuntimeError(f"resource_missing_hash:{resource.id}")
        source = Path(resource.file_path)
        if not source.exists():
            raise RuntimeError(f"resource_missing_file:{resource.file_path}")
        suffix = source.suffix or Path(resource.name).suffix or ".bin"
        relative = (
            Path("resources") / resource.content_hash[:2] / f"{resource.content_hash}{suffix}"
        )
        destination = output_dir / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            _assert_file_identity(destination, resource.content_hash, resource.size_bytes)
        else:
            if config.resource_policy == "hardlink":
                destination.hardlink_to(source)
            else:
                shutil.copy2(source, destination)
            _assert_file_identity(destination, resource.content_hash, resource.size_bytes)
            copied_bytes += resource.size_bytes
        descriptors.append(
            {
                "id": str(resource.id),
                "name": resource.name,
                "kind": resource.kind,
                "mime_type": resource.mime_type,
                "size_bytes": resource.size_bytes,
                "sha256": resource.content_hash,
                "export_path": relative.as_posix(),
                "metadata": resource.metadata_json,
            }
        )
    return descriptors, copied_bytes


def _run_row(
    config: ShardedExportConfig, run: RunRecord, resources: list[dict[str, object]]
) -> dict[str, object]:
    return {
        "dataset": config.dataset,
        "batch": config.batch,
        "run_id": str(run.id),
        "experiment_id": str(run.experiment_id),
        "workflow_definition_id": str(run.workflow_definition_id),
        "benchmark_type": run.benchmark_type,
        "instance_key": run.instance_key,
        "sample_id": run.sample_id,
        "status": str(run.status),
        "created_at": run.created_at.isoformat(),
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "observed_fields_json": _json_string(run.summary_json.get("observed_fields", {})),
        "missing_fields_json": _json_string(run.summary_json.get("missing_fields", [])),
        "summary_json": _json_string(run.summary_json),
        "resources_json": _json_string(resources),
    }


def _load_reducer_rows(
    *, session: Session, config: ShardedExportConfig, runs: list[RunRecord]
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for run in runs:
        reducers = session.exec(select(RunReducer).where(RunReducer.run_id == run.id))
        for reducer in reducers:
            rows.append(
                {
                    "dataset": config.dataset,
                    "batch": config.batch,
                    "run_id": str(run.id),
                    "reducer_id": str(reducer.id),
                    "name": reducer.name,
                    "kind": reducer.kind,
                    "implementation_ref": reducer.implementation_ref,
                    "status": reducer.status,
                    "created_at": reducer.created_at.isoformat(),
                    "input_scope_json": _json_string(reducer.input_scope_json),
                    "output_json": _json_string(reducer.output_json),
                    "config_json": _json_string(reducer.config_json),
                }
            )
    return rows


def _load_drop_rows(
    *, session: Session, config: ShardedExportConfig, runs: list[RunRecord]
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for run in runs:
        reducers = list(session.exec(select(RunReducer).where(RunReducer.run_id == run.id)))
        for reducer in reducers:
            drops = session.exec(
                select(RunDropsManifest).where(RunDropsManifest.reducer_id == reducer.id)
            )
            for drop in drops:
                rows.append(
                    {
                        "dataset": config.dataset,
                        "batch": config.batch,
                        "run_id": str(run.id),
                        "reducer_id": str(reducer.id),
                        "drop_id": str(drop.id),
                        "loss_class": drop.loss_class,
                        "dropped_source_kind": drop.dropped_source_kind,
                        "dropped_field_path": drop.dropped_field_path,
                        "reason": drop.reason,
                        "affected_analysis": drop.affected_analysis,
                        "declaration_kind": drop.declaration_kind,
                        "evidence_json": _json_string(drop.evidence_json),
                        "created_at": drop.created_at.isoformat(),
                    }
                )
    return rows


def _write_shards(
    output_dir: Path,
    family: str,
    rows: list[dict[str, object]],
    config: ShardedExportConfig,
    checksums: dict[str, str],
) -> list[ShardRecord]:
    records: list[ShardRecord] = []
    for index, batch in enumerate(_shard_batches(rows, config.shard_size_bytes)):
        name = f"{family}-{index:05d}.parquet"
        relative = Path(family) / name
        final_path = output_dir / relative
        tmp_path = final_path.with_suffix(final_path.suffix + ".tmp")
        table = pa.Table.from_pylist(batch)
        pq.write_table(table, tmp_path)
        tmp_path.replace(final_path)
        digest = _sha256_file(final_path)
        checksums[relative.as_posix()] = digest
        records.append(
            ShardRecord(
                name=name,
                family=family,  # type: ignore[arg-type]
                path=relative.as_posix(),
                row_count=len(batch),
                size_bytes=final_path.stat().st_size,
                sha256=digest,
            )
        )
    return records


def _shard_batches(
    rows: list[dict[str, object]], shard_size_bytes: int
) -> Iterable[list[dict[str, object]]]:
    batch: list[dict[str, object]] = []
    size = 0
    for row in rows:
        encoded_size = len(_json_string(row).encode())
        if batch and size + encoded_size > shard_size_bytes:
            yield batch
            batch = []
            size = 0
        batch.append(row)
        size += encoded_size
    if batch:
        yield batch


def _malformed_source_records(runs: list[RunRecord]) -> int:
    return sum(
        1 for run in runs if "source_parse_error" in run.summary_json.get("observed_fields", {})
    )


def _assert_file_identity(path: Path, expected_sha256: str, expected_size: int) -> None:
    if path.stat().st_size != expected_size:
        raise RuntimeError(f"resource_size_mismatch:{path}")
    if _sha256_file(path) != expected_sha256:
        raise RuntimeError(f"resource_hash_mismatch:{path}")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_string(value: object) -> str:
    return json.dumps(value, allow_nan=False, sort_keys=True, separators=(",", ":"))


def _write_text(path: Path, text: str) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(text)
    tmp_path.replace(path)
