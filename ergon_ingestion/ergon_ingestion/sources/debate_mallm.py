"""DEBATE / MALLM source parser for nested multi-agent deliberation traces."""

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
from ergon_ingestion.reducers.debate_mallm import default_reducers

Record = dict[str, object]


class DebateMallmImporter:
    """Read local DEBATE / MALLM JSON/JSONL nested full-trace records."""

    info = ImporterInfo(
        slug="debate_mallm",
        display_name="DEBATE / MALLM",
        schema_fit_class="full-trace",
        supported_formats=["jsonl", "json"],
        export_claim="conditional",
        default_reducers=[
            "debate_mallm.final_answer",
            "debate_mallm.deliberation_trace",
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
            warnings=[
                "debate_mallm may omit private prompts, model configs, and judge rubric details"
            ],
        )

    def iter_runs(self, source: ImportSource) -> Iterator[ParsedRun]:
        report = self.validate(source)
        if not report.ok:
            raise FileNotFoundError("; ".join(report.errors))
        for idx, record in enumerate(iter_debate_mallm_records(source.input_path), start=1):
            yield parse_debate_mallm_record(record, fallback_id=f"row-{idx}")


def iter_debate_mallm_records(path: Path) -> Iterator[Record]:
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


def parse_debate_mallm_record(record: Record, *, fallback_id: str = "row-1") -> ParsedRun:
    source_id = _source_run_id(record, fallback_id=fallback_id)
    task_id = _task_id(record)
    question = _question(record)
    rounds = _rounds(record)
    messages = _flat_messages(rounds)
    judgement = _judgement(record)

    return ParsedRun(
        source_run_id=source_id,
        instance_key=task_id or source_id,
        description=f"Imported DEBATE / MALLM deliberation {source_id}",
        schema_fit_class="full-trace",
        observed_fields={
            "debate_id": record.get("debate_id") or record.get("conversation_id"),
            "task_id": task_id,
            "question": question,
            "rounds": rounds,
            "final_answer": record.get("final_answer"),
            "votes": record.get("votes"),
            "judge": record.get("judge"),
            "judge_score": record.get("judge_score"),
            "correct": record.get("correct"),
        },
        missing_fields=_missing_fields(record),
        annotations=[
            ParsedAnnotation(
                namespace="debate_mallm.task",
                payload={"task_id": task_id, "question": question},
            ),
            ParsedAnnotation(namespace="debate_mallm.judgement", payload=judgement),
        ],
        events=_events(record, rounds),
        resources=_resources(record, rounds, messages, judgement),
        reducers=default_reducers(record),
    )


def _planned_runs(path: Path) -> int:
    if path.suffix == ".jsonl":
        return sum(1 for line in path.read_text().splitlines() if line.strip())
    data = json.loads(path.read_text())
    if isinstance(data, list):
        return len(data)
    return 1


def _events(record: Record, rounds: list[Record]) -> list[ParsedEvent]:
    events: list[ParsedEvent] = []
    for round_index, round_record in enumerate(rounds, start=1):
        round_number = _round_number(round_record, round_index)
        events.append(
            ParsedEvent(
                sequence=len(events),
                event_type="round.start",
                payload={"round": round_number, "round_index": round_index - 1},
            )
        )
        for turn_index, turn in enumerate(_agent_turns(round_record)):
            agent = _agent(turn)
            events.append(
                ParsedEvent(
                    sequence=len(events),
                    event_type="agent_turn",
                    payload={
                        "round": round_number,
                        "agent": agent,
                        "content": turn.get("content"),
                        "turn_index": turn_index,
                    },
                )
            )
            for message_index, message in enumerate(_messages(turn)):
                events.append(
                    ParsedEvent(
                        sequence=len(events),
                        event_type="agent_message",
                        payload={
                            "round": round_number,
                            "agent": agent,
                            "role": message.get("role"),
                            "content": message.get("content"),
                            "turn_index": turn_index,
                            "message_index": message_index,
                        },
                    )
                )

    if record.get("final_answer") is not None:
        events.append(
            ParsedEvent(
                sequence=len(events),
                event_type="final_answer",
                payload={"final_answer": record.get("final_answer")},
            )
        )

    judgement = _judgement(record)
    if any(value is not None for value in judgement.values()):
        events.append(ParsedEvent(sequence=len(events), event_type="judge_vote", payload=judgement))
    return events


def _resources(
    record: Record,
    rounds: list[Record],
    messages: list[Record],
    judgement: Record,
) -> list[ParsedResource]:
    resources = [
        ParsedResource(
            name="source-record.json",
            kind="import",
            mime_type="application/json",
            payload=record,
        )
    ]
    if rounds:
        resources.append(
            ParsedResource(
                name="rounds.json",
                kind="artifact",
                mime_type="application/json",
                payload={"rounds": rounds},
            )
        )
    if messages:
        resources.append(
            ParsedResource(
                name="messages.json",
                kind="artifact",
                mime_type="application/json",
                payload={"messages": messages},
            )
        )
    if record.get("final_answer") is not None:
        resources.append(
            ParsedResource(
                name="final-answer.txt",
                kind="output",
                mime_type="text/plain",
                payload=str(record.get("final_answer")),
            )
        )
    if any(value is not None for value in judgement.values()):
        resources.append(
            ParsedResource(
                name="judgement.json",
                kind="report",
                mime_type="application/json",
                payload=judgement,
            )
        )
    return resources


def _source_run_id(record: Record, *, fallback_id: str) -> str:
    value = (
        record.get("debate_id")
        or record.get("conversation_id")
        or record.get("source_run_id")
        or record.get("run_id")
    )
    return fallback_id if value is None else str(value)


def _task_id(record: Record) -> str:
    task = _task(record)
    value = record.get("task_id") or task.get("id") or task.get("task_id")
    return "" if value is None else str(value)


def _question(record: Record) -> object:
    task = _task(record)
    return record.get("question") or task.get("question") or task.get("prompt")


def _task(record: Record) -> Record:
    value = record.get("task")
    return value if isinstance(value, dict) else {}


def _rounds(record: Record) -> list[Record]:
    value = record.get("rounds")
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _agent_turns(round_record: Record) -> list[Record]:
    value = round_record.get("agent_turns") or round_record.get("turns")
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _messages(turn: Record) -> list[Record]:
    value = turn.get("messages")
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _flat_messages(rounds: list[Record]) -> list[Record]:
    messages: list[Record] = []
    for round_index, round_record in enumerate(rounds, start=1):
        round_number = _round_number(round_record, round_index)
        for turn_index, turn in enumerate(_agent_turns(round_record)):
            agent = _agent(turn)
            for message_index, message in enumerate(_messages(turn)):
                payload = {
                    "round": round_number,
                    "agent": agent,
                    "turn_index": turn_index,
                    "message_index": message_index,
                }
                payload.update(message)
                messages.append(payload)
    return messages


def _agent(turn: Record) -> str:
    value = turn.get("agent") or turn.get("agent_id") or turn.get("speaker")
    return "" if value is None else str(value)


def _round_number(round_record: Record, fallback: int) -> object:
    return round_record.get("round") or round_record.get("round_index") or fallback


def _judgement(record: Record) -> Record:
    return {
        "votes": record.get("votes"),
        "judge": record.get("judge"),
        "judge_score": record.get("judge_score"),
        "correct": record.get("correct"),
    }


def _missing_fields(record: Record) -> list[str]:
    missing: list[str] = []
    for field_path in ["private_prompts", "model_configs", "judge_rubric"]:
        if _missing(record.get(field_path)):
            missing.append(field_path)
    return missing


def _missing(value: object) -> bool:
    return value is None or value == "" or value == [] or value == {}


def _as_record(value: object) -> Record:
    if isinstance(value, dict):
        return value
    return {"value": value}
