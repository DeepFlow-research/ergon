"""Verification for Ergon-native sharded exports."""

import hashlib
import json
from pathlib import Path

import pyarrow.parquet as pq


TRUNCATION_MARKERS = ("[truncated]", "... truncated", "<truncated>")


def verify_export(export_dir: Path) -> dict[str, object]:
    """Verify manifest counts, shard hashes, resource hashes, and truncation markers."""

    manifest_path = export_dir / "manifest.json"
    checksums_path = export_dir / "checksums.json"
    if not manifest_path.exists():
        raise RuntimeError(f"missing_manifest:{manifest_path}")
    manifest = json.loads(manifest_path.read_text())
    checksums = json.loads(checksums_path.read_text()) if checksums_path.exists() else {}

    counts = {"runs": 0, "reducers": 0, "drops": 0}
    resources_checked = 0
    truncation_hits: list[str] = []
    for family in ("runs", "reducers", "drops"):
        for shard in manifest["shards"].get(family, []):
            path, rows = _verify_shard(export_dir, shard, checksums)
            counts[family] += len(rows)
            if family == "runs":
                resources_checked += _verify_run_rows(export_dir, path, rows, truncation_hits)

    if counts["runs"] != manifest["run_count"]:
        raise RuntimeError("manifest_run_count_mismatch")
    if counts["reducers"] != manifest["reducer_count"]:
        raise RuntimeError("manifest_reducer_count_mismatch")
    if counts["drops"] != manifest["drop_count"]:
        raise RuntimeError("manifest_drop_count_mismatch")
    if resources_checked != manifest["resource_count"]:
        raise RuntimeError("manifest_resource_count_mismatch")
    if truncation_hits:
        raise RuntimeError(f"truncation_markers:{truncation_hits[:5]}")
    return {
        "ok": True,
        "run_count": counts["runs"],
        "reducer_count": counts["reducers"],
        "drop_count": counts["drops"],
        "resource_count": resources_checked,
    }


def _verify_shard(
    export_dir: Path, shard: dict[str, object], checksums: dict[str, str]
) -> tuple[Path, list[dict[str, object]]]:
    path = export_dir / str(shard["path"])
    if not path.exists():
        raise RuntimeError(f"missing_shard:{path}")
    actual_hash = _sha256_file(path)
    if shard["sha256"] != actual_hash or checksums.get(str(shard["path"])) != actual_hash:
        raise RuntimeError(f"shard_hash_mismatch:{path}")
    rows = pq.read_table(path).to_pylist()
    if len(rows) != shard["row_count"]:
        raise RuntimeError(f"shard_row_count_mismatch:{path}")
    return path, rows


def _verify_run_rows(
    export_dir: Path,
    shard_path: Path,
    rows: list[dict[str, object]],
    truncation_hits: list[str],
) -> int:
    resources_checked = 0
    for row_index, row in enumerate(rows):
        if _contains_truncation_marker(row):
            truncation_hits.append(f"{shard_path}:{row_index}")
        resources = json.loads(str(row.get("resources_json") or "[]"))
        for resource in resources:
            _verify_resource(export_dir, resource)
            resources_checked += 1
    return resources_checked


def _verify_resource(export_dir: Path, resource: dict[str, object]) -> None:
    path = export_dir / str(resource["export_path"])
    if not path.exists():
        raise RuntimeError(f"missing_resource:{path}")
    if path.stat().st_size != resource["size_bytes"]:
        raise RuntimeError(f"resource_size_mismatch:{path}")
    if _sha256_file(path) != resource["sha256"]:
        raise RuntimeError(f"resource_hash_mismatch:{path}")


def _contains_truncation_marker(value: object) -> bool:
    if isinstance(value, str):
        return any(marker in value.lower() for marker in TRUNCATION_MARKERS)
    if isinstance(value, dict):
        return any(_contains_truncation_marker(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_truncation_marker(item) for item in value)
    return False


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
