"""Persist parsed public artifact records into Ergon's run spine."""

import hashlib
import json
import math
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from sqlmodel import Session

from ergon_core.core.persistence.definitions.models import (
    ExperimentDefinition,
    ExperimentDefinitionInstance,
    ExperimentDefinitionTask,
)
from ergon_core.core.persistence.graph.models import RunGraphAnnotation, RunGraphNode
from ergon_core.core.persistence.shared.enums import RunResourceKind, RunStatus, TaskExecutionStatus
from ergon_core.core.persistence.telemetry.models import (
    RunRecord,
    RunResource,
    RunTaskExecution,
)
from ergon_ingestion.models import ImportSource, ParsedResource, ParsedRun


MAX_DB_JSON_BYTES = 8 * 1024 * 1024
MAX_DB_JSON_FIELD_BYTES = 512 * 1024


class WriteRunResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: UUID
    task_id: UUID
    task_execution_id: UUID


class ExternalRunWriter:
    """Write parsed public artifacts as imported Ergon runs."""

    def __init__(self, *, session: Session, source: ImportSource, blob_root: Path) -> None:
        self._session = session
        self._source = source
        self._blob_root = blob_root
        self._definition: ExperimentDefinition | None = None

    def write_run(self, parsed: ParsedRun) -> WriteRunResult:
        definition = self._definition_row()
        observed_fields = _compact_for_db(_json_safe(parsed.observed_fields))
        missing_fields = _json_safe(parsed.missing_fields)
        instance = ExperimentDefinitionInstance(
            experiment_definition_id=definition.id,
            instance_key=parsed.instance_key,
            benchmark_instance_state={
                "imported": True,
                "source_run_id": parsed.source_run_id,
                "schema_fit_class": parsed.schema_fit_class,
                "observed_fields": observed_fields,
                "missing_fields": missing_fields,
            },
        )
        self._session.add(instance)
        self._session.flush()

        task = ExperimentDefinitionTask(
            experiment_definition_id=definition.id,
            instance_id=instance.id,
            task_slug="imported-root",
            task_type="imported",
            description=parsed.description,
            task_payload_json={
                "field_provenance": "required-spine",
                "source_run_id": parsed.source_run_id,
            },
        )
        self._session.add(task)
        self._session.flush()

        run = RunRecord(
            definition_id=definition.id,
            benchmark_type=f"imported:{self._source.dataset}",
            instance_key=parsed.instance_key,
            sample_id=parsed.source_run_id,
            status=RunStatus.COMPLETED,
            summary_json={
                "imported": True,
                "source_slug": self._source.dataset,
                "import_batch_id": self._source.batch_id,
                "source_run_id": parsed.source_run_id,
                "source_unit_kind": parsed.schema_fit_class,
                "observed_fields": observed_fields,
                "missing_fields": missing_fields,
            },
        )
        self._session.add(run)
        self._session.flush()

        node = RunGraphNode(
            run_id=run.id,
            task_id=task.id,
            instance_key=parsed.instance_key,
            task_slug="imported-root",
            description=parsed.description,
            status="completed",
        )
        self._session.add(node)
        self._session.flush()

        execution = RunTaskExecution(
            run_id=run.id,
            task_id=node.task_id,
            status=TaskExecutionStatus.COMPLETED,
            output_json={
                "imported": True,
                "source_run_id": parsed.source_run_id,
                "resources": [resource.name for resource in parsed.resources],
            },
        )
        self._session.add(execution)
        self._session.flush()

        for sequence, annotation in enumerate(parsed.annotations, start=1):
            self._session.add(
                RunGraphAnnotation(
                    run_id=run.id,
                    target_type="node",
                    target_id=node.task_id,
                    namespace=annotation.namespace,
                    sequence=sequence,
                    payload=_json_safe(annotation.payload),
                )
            )

        for resource in parsed.resources:
            self._session.add(self._resource_row(run.id, execution.id, resource))

        return WriteRunResult(run_id=run.id, task_id=node.task_id, task_execution_id=execution.id)

    def _definition_row(self) -> ExperimentDefinition:
        if self._definition is None:
            self._definition = ExperimentDefinition(
                benchmark_type=f"imported:{self._source.dataset}",
                name=f"imported:{self._source.dataset}",
                metadata_json={
                    "imported": True,
                    "source_slug": self._source.dataset,
                    "import_batch_id": self._source.batch_id,
                    "source_url": self._source.source_url,
                    "source_version_ref": self._source.source_version_ref,
                    "source_license": self._source.source_license,
                    "redistribution_class": self._source.redistribution_class,
                },
            )
            self._session.add(self._definition)
            self._session.flush()
        return self._definition

    def _resource_row(
        self,
        run_id: UUID,
        task_execution_id: UUID,
        resource: ParsedResource,
    ) -> RunResource:
        path, content_hash, size = self._materialize_resource(run_id, resource)
        return RunResource(
            run_id=run_id,
            task_execution_id=task_execution_id,
            kind=RunResourceKind(resource.kind).value,
            name=resource.name,
            mime_type=resource.mime_type,
            file_path=str(path),
            size_bytes=size,
            content_hash=content_hash,
            metadata_json={"imported": True, "source_slug": self._source.dataset},
        )

    def _materialize_resource(
        self,
        run_id: UUID,
        resource: ParsedResource,
    ) -> tuple[Path, str, int]:
        if resource.path is not None:
            data = resource.path.read_bytes()
            suffix = resource.path.suffix
        elif isinstance(resource.payload, str):
            data = resource.payload.encode()
            suffix = Path(resource.name).suffix
        else:
            data = json.dumps(
                _json_safe(resource.payload or {}),
                allow_nan=False,
                sort_keys=True,
            ).encode()
            suffix = Path(resource.name).suffix or ".json"
        content_hash = hashlib.sha256(data).hexdigest()
        directory = self._blob_root / str(run_id)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{content_hash}{suffix}"
        path.write_bytes(data)
        return path, content_hash, len(data)


def _json_safe(value: object) -> object:
    if not isinstance(value, (str, bytes, bytearray)):
        try:
            tolist = value.tolist
        except AttributeError:
            tolist = None
        if tolist is not None:
            return _json_safe(tolist())
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    return value


def _compact_for_db(value: object) -> object:
    if _json_size(value) <= MAX_DB_JSON_BYTES:
        return value
    if isinstance(value, dict):
        compacted = {
            key: _compaction_marker(item) if _json_size(item) > MAX_DB_JSON_FIELD_BYTES else item
            for key, item in value.items()
        }
        if _json_size(compacted) <= MAX_DB_JSON_BYTES:
            return compacted
    return _compaction_marker(value)


def _compaction_marker(value: object) -> dict[str, object]:
    data = _json_bytes(value)
    return {
        "_ergon_compacted": True,
        "reason": "oversized_db_metadata",
        "original_type": type(value).__name__,
        "size_bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "materialized_in_resources": True,
    }


def _json_size(value: object) -> int:
    return len(_json_bytes(value))


def _json_bytes(value: object) -> bytes:
    return json.dumps(value, allow_nan=False, sort_keys=True).encode()
