"""Agent Reward Bench source parser for annotated reward/preference trajectories."""

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
from ergon_ingestion.reducers.agent_reward_bench import default_reducers

Record = dict[str, object]


class AgentRewardBenchImporter:
    """Read local Agent Reward Bench JSON/JSONL full-trace reward annotations."""

    info = ImporterInfo(
        slug="agent_reward_bench",
        display_name="Agent Reward Bench",
        schema_fit_class="full-trace",
        supported_formats=["jsonl", "json"],
        export_claim="conditional",
        default_reducers=[
            "agent_reward_bench.reward_label",
            "agent_reward_bench.process_trace",
        ],
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
            warnings=["agent_reward_bench may lack independent rejudge provenance"],
        )

    def iter_runs(self, source: ImportSource) -> Iterator[ParsedRun]:
        report = self.validate(source)
        if not report.ok:
            raise FileNotFoundError("; ".join(report.errors))
        for idx, record in enumerate(iter_agent_reward_bench_records(source.input_path), start=1):
            yield parse_agent_reward_bench_record(record, fallback_id=f"row-{idx}")


def iter_agent_reward_bench_records(path: Path) -> Iterator[Record]:
    if path.suffix == ".jsonl":
        for line in path.read_text().splitlines():
            if line.strip():
                yield _as_record(json.loads(line))
        return

    data = json.loads(path.read_text())
    if isinstance(data, list):
        for item in data:
            yield _as_record(item)
        return
    yield _as_record(data)


def parse_agent_reward_bench_record(
    record: Record,
    *,
    fallback_id: str = "row-1",
) -> ParsedRun:
    source_id = _source_run_id(record, fallback_id=fallback_id)
    task_id = _task_id(record)
    messages = _messages(record)
    actions = _actions(record)
    tool_calls = _tool_calls(record, messages)
    process_trace = _process_trace(record)

    return ParsedRun(
        source_run_id=source_id,
        instance_key=task_id or source_id,
        description=f"Imported Agent Reward Bench trajectory {source_id}",
        schema_fit_class="full-trace",
        observed_fields={
            "trajectory_id": source_id,
            "task_id": task_id,
            "reward_score": record.get("reward_score"),
            "preference_label": record.get("preference_label"),
            "judge": record.get("judge"),
            "annotator": record.get("annotator"),
            "annotation_metadata": record.get("annotation_metadata"),
            "process_trace": process_trace,
        },
        missing_fields=_missing_fields(record),
        annotations=[
            ParsedAnnotation(
                namespace="agent_reward_bench.labels",
                payload={
                    "reward_score": record.get("reward_score"),
                    "preference_label": record.get("preference_label"),
                },
            ),
            ParsedAnnotation(
                namespace="agent_reward_bench.annotation_provenance",
                payload={
                    "judge": record.get("judge"),
                    "annotator": record.get("annotator"),
                    "annotation_metadata": record.get("annotation_metadata"),
                },
            ),
        ],
        events=_events_from_trace(messages, actions),
        resources=_resources(record, messages, actions, tool_calls, process_trace),
        reducers=default_reducers(record),
    )


def _planned_runs(path: Path) -> int:
    if path.suffix == ".jsonl":
        return sum(1 for line in path.read_text().splitlines() if line.strip())
    data = json.loads(path.read_text())
    if isinstance(data, list):
        return len(data)
    return 1


def _events_from_trace(messages: list[Record], actions: list[Record]) -> list[ParsedEvent]:
    events: list[ParsedEvent] = []
    emitted_action_indexes: set[int] = set()

    for message_index, message in enumerate(messages):
        role = str(message.get("role", "unknown"))
        if role == "tool":
            events.append(
                ParsedEvent(
                    sequence=len(events),
                    event_type="tool_result",
                    payload={
                        "tool_call_id": message.get("tool_call_id"),
                        "name": message.get("name"),
                        "content": message.get("content"),
                        "message_index": message_index,
                    },
                )
            )
            continue

        events.append(
            ParsedEvent(
                sequence=len(events),
                event_type=f"message.{role}",
                payload={key: value for key, value in message.items() if key != "tool_calls"},
            )
        )
        for tool_call in _message_tool_calls(message):
            events.append(
                ParsedEvent(
                    sequence=len(events),
                    event_type="tool_call",
                    payload={
                        "id": tool_call.get("id"),
                        "name": tool_call.get("name"),
                        "args": tool_call.get("args"),
                        "message_index": message_index,
                    },
                )
            )
            action_index = _matching_action_index(actions, tool_call)
            if action_index is not None and action_index not in emitted_action_indexes:
                events.append(_action_event(actions[action_index], action_index, len(events)))
                emitted_action_indexes.add(action_index)

    for action_index, action in enumerate(actions):
        if action_index not in emitted_action_indexes:
            events.append(_action_event(action, action_index, len(events)))

    return events


def _action_event(action: Record, action_index: int, sequence: int) -> ParsedEvent:
    payload = {
        "name": action.get("name"),
        "order": action_index,
        "tool_call_id": action.get("tool_call_id"),
        "arguments": action.get("arguments"),
    }
    if "reward_delta" in action:
        payload["reward_delta"] = action.get("reward_delta")
    return ParsedEvent(sequence=sequence, event_type="action", payload=payload)


def _resources(
    record: Record,
    messages: list[Record],
    actions: list[Record],
    tool_calls: list[Record],
    process_trace: list[object],
) -> list[ParsedResource]:
    resources = [
        ParsedResource(
            name="source-record.json",
            kind="import",
            mime_type="application/json",
            payload=record,
        ),
        ParsedResource(
            name="messages.json",
            kind="artifact",
            mime_type="application/json",
            payload={"messages": messages},
        ),
    ]
    if actions:
        resources.append(
            ParsedResource(
                name="actions.json",
                kind="artifact",
                mime_type="application/json",
                payload={"actions": actions},
            )
        )
    if tool_calls:
        resources.append(
            ParsedResource(
                name="tool-calls.json",
                kind="artifact",
                mime_type="application/json",
                payload={"tool_calls": tool_calls},
            )
        )
    if process_trace:
        resources.append(
            ParsedResource(
                name="process-trace.json",
                kind="artifact",
                mime_type="application/json",
                payload={"process_trace": process_trace},
            )
        )
    return resources


def _source_run_id(record: Record, *, fallback_id: str) -> str:
    value = record.get("trajectory_id") or record.get("source_run_id") or record.get("run_id")
    return fallback_id if value is None else str(value)


def _task_id(record: Record) -> str:
    task = record.get("task")
    if isinstance(task, dict) and task.get("id") is not None:
        return str(task["id"])
    value = record.get("task_id")
    return "" if value is None else str(value)


def _messages(record: Record) -> list[Record]:
    value = record.get("messages")
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _actions(record: Record) -> list[Record]:
    value = record.get("actions")
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _tool_calls(record: Record, messages: list[Record]) -> list[Record]:
    explicit = record.get("tool_calls")
    if isinstance(explicit, list):
        return [item for item in explicit if isinstance(item, dict)]

    calls: list[Record] = []
    for message in messages:
        calls.extend(_message_tool_calls(message))
    return calls


def _message_tool_calls(message: Record) -> list[Record]:
    value = message.get("tool_calls")
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _matching_action_index(actions: list[Record], tool_call: Record) -> int | None:
    tool_call_id = tool_call.get("id")
    tool_name = tool_call.get("name")
    for index, action in enumerate(actions):
        if tool_call_id is not None and action.get("tool_call_id") == tool_call_id:
            return index
        if action.get("name") == tool_name:
            return index
    return None


def _process_trace(record: Record) -> list[object]:
    value = record.get("process_trace")
    if not isinstance(value, list):
        return []
    return value


def _missing_fields(record: Record) -> list[str]:
    missing: list[str] = []
    if _missing(record.get("independent_rejudge")):
        missing.append("independent_rejudge")
    if _missing(record.get("inter_annotator_agreement")):
        missing.append("inter_annotator_agreement")
    return missing


def _missing(value: object) -> bool:
    return value is None or value == "" or value == []


def _as_record(value: object) -> Record:
    if isinstance(value, dict):
        return value
    return {"value": value}
