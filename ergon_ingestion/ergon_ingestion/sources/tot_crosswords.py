"""Tree-of-Thought crossword DFS trace importer."""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from ergon_ingestion.models import (
    ImporterInfo,
    ImportSource,
    ParsedAnnotation,
    ParsedEvent,
    ParsedResource,
    ParsedRun,
    ValidationReport,
)
from ergon_ingestion.reducers.tot import (
    final_reward,
    missing_internal_fields,
    search_efficiency,
    search_efficiency_output,
)


class TotCrosswordsImporter:
    """Parse paired prune/no-prune Tree-of-Thought crossword JSON traces."""

    info = ImporterInfo(
        slug="tot_crosswords",
        display_name="Tree-of-Thought crossword DFS traces",
        schema_fit_class="full-trace",
        supported_formats=["json"],
        export_claim="safe",
        paper_result_ids=["rq1.tot_crosswords.search_efficiency"],
        default_reducers=["tot.final_reward", "tot.search_efficiency"],
    )

    def validate(self, source: ImportSource) -> ValidationReport:
        if not source.input_path.exists():
            return ValidationReport(
                dataset=self.info.slug,
                input_path=source.input_path,
                ok=False,
                errors=[f"input path does not exist: {source.input_path}"],
            )
        try:
            planned_runs = len(_load_trace_records(source.input_path))
        except (OSError, ValueError, TypeError) as exc:
            return ValidationReport(
                dataset=self.info.slug,
                input_path=source.input_path,
                ok=False,
                errors=[f"could not parse ToT crossword traces: {exc}"],
            )
        return ValidationReport(
            dataset=self.info.slug,
            input_path=source.input_path,
            ok=True,
            planned_runs=planned_runs,
        )

    def iter_runs(self, source: ImportSource) -> Iterator[ParsedRun]:
        report = self.validate(source)
        if not report.ok:
            raise ValueError("; ".join(report.errors))
        for record in _load_trace_records(source.input_path):
            yield parsed_run_from_trace(record)


def parsed_run_from_trace(record: dict[str, Any]) -> ParsedRun:
    puzzle_id = str(record["puzzle_id"])
    policy = str(record["policy"])
    source_run_id = f"{puzzle_id}:{policy}"
    search_shape = search_efficiency_output(record)
    search_shape.pop("reward_per_visited_state", None)
    search_shape = {"policy": policy} | search_shape
    return ParsedRun(
        source_run_id=source_run_id,
        instance_key=puzzle_id,
        description=f"Tree-of-Thought crossword trace {puzzle_id} with {policy}",
        schema_fit_class="full-trace",
        observed_fields=record,
        missing_fields=missing_internal_fields(record),
        annotations=[
            ParsedAnnotation(
                namespace="tot.trace_identity",
                payload={"puzzle_id": puzzle_id, "policy": policy},
            ),
            ParsedAnnotation(namespace="tot.search_shape", payload=search_shape),
        ],
        events=_events_from_trace(record, policy=policy),
        resources=[
            ParsedResource(
                name="tot-trace.json",
                kind="artifact",
                mime_type="application/json",
                payload=record,
            )
        ],
        reducers=[final_reward(record), search_efficiency(record)],
    )


def _load_trace_records(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text())
    if isinstance(data, dict) and isinstance(data.get("traces"), list):
        records = data["traces"]
    elif isinstance(data, list):
        records = data
    else:
        records = [data]
    return [_as_record(record) for record in records]


def _as_record(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError("ToT trace records must be JSON objects")
    if "puzzle_id" not in value or "policy" not in value:
        raise ValueError("ToT trace records require puzzle_id and policy")
    return value


def _events_from_trace(record: dict[str, Any], *, policy: str) -> list[ParsedEvent]:
    events: list[ParsedEvent] = []
    for action in _list(record.get("actions")):
        events.append(
            ParsedEvent(
                sequence=len(events) + 1,
                event_type="tot.action",
                payload=_payload(action, key="action") | {"policy": policy},
            )
        )
    for state in _list(record.get("states")):
        events.append(
            ParsedEvent(
                sequence=len(events) + 1,
                event_type="tot.state",
                payload=_payload(state, key="state") | {"policy": policy},
            )
        )
    return events


def _payload(value: Any, *, key: str) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {key: value}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []
