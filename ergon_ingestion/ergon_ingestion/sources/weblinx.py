"""WebLINX source parser for web interaction and chat traces."""

import gzip
import json
from collections.abc import Iterator
from pathlib import Path

from ergon_ingestion.models import (
    ImporterInfo,
    ImportSource,
    ParsedAnnotation,
    ParsedEvent,
    ParsedResource,
    ParsedRun,
    ValidationReport,
)
from ergon_ingestion.reducers.weblinx import default_reducers

Record = dict[str, object]


class WebLinxImporter:
    """Read local WebLINX JSON, JSONL, and JSON.GZ trace exports."""

    info = ImporterInfo(
        slug="weblinx",
        display_name="WebLINX",
        schema_fit_class="full-trace",
        supported_formats=["json", "jsonl", "json.gz"],
        export_claim="conditional",
        default_reducers=["weblinx.success", "weblinx.action_path"],
    )

    def validate(self, source: ImportSource) -> ValidationReport:
        if not source.input_path.exists():
            return ValidationReport(
                dataset=self.info.slug,
                input_path=source.input_path,
                ok=False,
                errors=[f"input path does not exist: {source.input_path}"],
            )
        return ValidationReport(
            dataset=self.info.slug,
            input_path=source.input_path,
            ok=True,
            planned_runs=_planned_runs(source.input_path),
            warnings=["weblinx external DOM/screenshot/replay artifacts are not imported"],
        )

    def iter_runs(self, source: ImportSource) -> Iterator[ParsedRun]:
        report = self.validate(source)
        if not report.ok:
            raise FileNotFoundError("; ".join(report.errors))
        for idx, record in enumerate(iter_weblinx_records(source.input_path), start=1):
            yield parse_weblinx_record(record, fallback_id=f"row-{idx}")


def iter_weblinx_records(path: Path) -> Iterator[Record]:
    text = _read_text(path)
    if _is_jsonl(path):
        for line in text.splitlines():
            if line.strip():
                yield _as_record(json.loads(line))
        return

    data = json.loads(text)
    if isinstance(data, list):
        for item in data:
            yield _as_record(item)
        return
    yield _as_record(data)


def parse_weblinx_record(record: Record, *, fallback_id: str = "row-1") -> ParsedRun:
    source_id = _source_run_id(record, fallback_id=fallback_id)
    session_id = _string(record.get("session_id") or record.get("session") or source_id)
    utterances = _utterances(record)
    actions = _actions(record)

    return ParsedRun(
        source_run_id=source_id,
        instance_key=session_id,
        description=f"Imported WebLINX web interaction trace {source_id}",
        schema_fit_class="full-trace",
        observed_fields={
            "demo_id": record.get("demo_id"),
            "session_id": record.get("session_id"),
            "success": record.get("success"),
            "outcome": record.get("outcome"),
        },
        missing_fields=[
            "dom_snapshots",
            "screenshots",
            "browser_replay_environment",
        ],
        annotations=[
            ParsedAnnotation(
                namespace="weblinx.session",
                payload={"demo_id": record.get("demo_id"), "session_id": record.get("session_id")},
            ),
            ParsedAnnotation(
                namespace="weblinx.outcome",
                payload={
                    "success": record.get("success"),
                    "outcome": record.get("outcome"),
                    "eval": record.get("eval"),
                },
            ),
        ],
        events=_events(utterances, actions),
        resources=_resources(record, utterances, actions),
        reducers=default_reducers(record),
    )


def _planned_runs(path: Path) -> int:
    text = _read_text(path)
    if _is_jsonl(path):
        return sum(1 for line in text.splitlines() if line.strip())
    data = json.loads(text)
    if isinstance(data, list):
        return len(data)
    return 1


def _read_text(path: Path) -> str:
    if path.suffix == ".gz":
        with gzip.open(path, "rt") as handle:
            return handle.read()
    return path.read_text()


def _is_jsonl(path: Path) -> bool:
    return path.suffix == ".jsonl" or path.suffixes[-2:] == [".jsonl", ".gz"]


def _events(utterances: list[Record], actions: list[Record]) -> list[ParsedEvent]:
    events: list[ParsedEvent] = []
    for utterance_index, utterance in enumerate(utterances):
        role = str(utterance.get("role") or utterance.get("speaker") or "unknown")
        events.append(
            ParsedEvent(
                sequence=len(events),
                event_type=f"utterance.{role}",
                payload={**utterance, "utterance_index": utterance_index},
            )
        )
    for action_index, action in enumerate(actions):
        action_name = _action_name(action)
        events.append(
            ParsedEvent(
                sequence=len(events),
                event_type=f"browser_action.{action_name}",
                payload={**action, "action_index": action_index},
            )
        )
    return events


def _resources(
    record: Record, utterances: list[Record], actions: list[Record]
) -> list[ParsedResource]:
    resources = [
        ParsedResource(
            name="source-record.json",
            kind="import",
            mime_type="application/json",
            payload=record,
        ),
        ParsedResource(
            name="utterances.json",
            kind="artifact",
            mime_type="application/json",
            payload={"utterances": utterances},
        ),
        ParsedResource(
            name="actions.json",
            kind="artifact",
            mime_type="application/json",
            payload={"actions": actions},
        ),
    ]
    external_refs = _external_refs(record, actions)
    if external_refs:
        resources.append(
            ParsedResource(
                name="external-browser-artifacts.json",
                kind="note",
                mime_type="application/json",
                payload={"external_refs": external_refs},
            )
        )
    return resources


def _external_refs(record: Record, actions: list[Record]) -> list[Record]:
    refs: list[Record] = []
    for key in ["dom_ref", "dom_snapshot_ref", "screenshot_ref", "screenshot_url"]:
        if record.get(key) is not None:
            refs.append({"field": key, "value": record[key]})
    for action_index, action in enumerate(actions):
        for key in ["dom_ref", "dom_snapshot_ref", "screenshot_ref", "screenshot_url"]:
            if action.get(key) is not None:
                refs.append({"field": f"actions[{action_index}].{key}", "value": action[key]})
    return refs


def _source_run_id(record: Record, *, fallback_id: str) -> str:
    value = record.get("demo_id") or record.get("source_run_id") or record.get("run_id")
    return fallback_id if value is None else str(value)


def _utterances(record: Record) -> list[Record]:
    value = record.get("utterances")
    if not isinstance(value, list):
        value = record.get("messages")
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _actions(record: Record) -> list[Record]:
    value = record.get("actions")
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _action_name(action: Record) -> str:
    return str(action.get("type") or action.get("action") or action.get("name") or "unknown")


def _string(value: object) -> str:
    return "" if value is None else str(value)


def _as_record(value: object) -> Record:
    if isinstance(value, dict):
        return value
    return {"value": value}
