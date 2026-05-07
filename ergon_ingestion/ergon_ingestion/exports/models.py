"""Models for Ergon-native sharded exports."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

EXPORTER_VERSION = "ergon-sharded-export-v1"

ResourcePolicy = Literal["copy", "hardlink"]
ExportFormat = Literal["parquet", "jsonl"]


class ShardedExportConfig(BaseModel):
    """Runtime configuration for one dataset export."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    dataset: str
    batch: str
    output_dir: Path
    page_size: int = 1000
    shard_size_mb: float = 256
    resume: bool = True
    resource_policy: ResourcePolicy = "copy"
    format: ExportFormat = "parquet"
    source_url: str | None = None
    source_version_ref: str | None = None

    @property
    def shard_size_bytes(self) -> int:
        return max(1, int(self.shard_size_mb * 1024 * 1024))


class ShardRecord(BaseModel):
    """Manifest entry for a completed export shard."""

    name: str
    family: Literal["runs", "reducers", "drops"]
    path: str
    row_count: int
    size_bytes: int
    sha256: str


class ExportState(BaseModel):
    """Resumable state for an export directory."""

    phase: Literal["started", "completed"] = "started"
    dataset: str
    batch: str
    next_run_offset: int = 0
    completed_shards: list[str] = Field(default_factory=list)
    last_run_id: str | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DatasetExportManifest(BaseModel):
    """Top-level manifest for one dataset export."""

    dataset: str
    batch: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    exporter_version: str = EXPORTER_VERSION
    source_url: str | None = None
    source_version_ref: str | None = None
    run_count: int = 0
    reducer_count: int = 0
    drop_count: int = 0
    resource_count: int = 0
    resource_total_bytes: int = 0
    shards: dict[str, list[ShardRecord]] = Field(
        default_factory=lambda: {"runs": [], "reducers": [], "drops": []}
    )
    malformed_source_records: int = 0
    verification: dict[str, object] = Field(default_factory=dict)


def dump_model_json(model: BaseModel) -> str:
    """Serialize model JSON with stable key ordering for manifests and tests."""

    data = model.model_dump(mode="json")
    return json.dumps(data, indent=2, sort_keys=True) + "\n"
