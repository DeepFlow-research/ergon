"""Reducers for DEBATE / MALLM multi-agent deliberation records."""

from collections.abc import Iterable

from ergon_ingestion.models import ParsedDrop, ParsedReducer

Record = dict[str, object]

FINAL_ANSWER_FIELDS = ["final_answer", "votes", "judge", "judge_score", "correct"]
DELIBERATION_TRACE_FIELDS = [
    "rounds",
    "agent_turns",
    "messages",
    "final_answer",
    "votes",
    "judge_score",
    "correct",
]


def final_answer_reducer(record: Record) -> ParsedReducer:
    """Expose the source final answer with available vote/judge outcome fields."""

    return ParsedReducer(
        name="debate_mallm.final_answer",
        kind="original",
        output={
            "final_answer": record.get("final_answer"),
            "votes": record.get("votes"),
            "judge": record.get("judge"),
            "judge_score": record.get("judge_score"),
            "correct": record.get("correct"),
        },
        implementation_ref="ergon_ingestion.reducers.debate_mallm.final_answer_reducer",
        fields_read=FINAL_ANSWER_FIELDS,
        drops=_source_caveats(record, "debate_mallm.final_answer"),
    )


def deliberation_trace_reducer(record: Record) -> ParsedReducer:
    """Recover compact multi-agent deliberation features from nested rounds."""

    rounds = _rounds(record)
    turns = _agent_turns(rounds)
    messages = _messages(turns)
    return ParsedReducer(
        name="debate_mallm.deliberation_trace",
        kind="recovered",
        output={
            "round_count": len(rounds),
            "agent_turn_count": len(turns),
            "message_count": len(messages),
            "agents": _agents(turns),
            "rounds": _round_summaries(rounds),
            "final_answer": record.get("final_answer"),
            "votes": record.get("votes"),
            "judge_score": record.get("judge_score"),
            "correct": record.get("correct"),
        },
        implementation_ref="ergon_ingestion.reducers.debate_mallm.deliberation_trace_reducer",
        fields_read=DELIBERATION_TRACE_FIELDS,
        drops=_source_caveats(record, "debate_mallm.deliberation_trace"),
    )


def default_reducers(record: Record) -> list[ParsedReducer]:
    return [final_answer_reducer(record), deliberation_trace_reducer(record)]


def _rounds(record: Record) -> list[Record]:
    value = record.get("rounds")
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _agent_turns(rounds: Iterable[Record]) -> list[Record]:
    turns: list[Record] = []
    for round_record in rounds:
        value = round_record.get("agent_turns") or round_record.get("turns")
        if isinstance(value, list):
            turns.extend(item for item in value if isinstance(item, dict))
    return turns


def _messages(turns: Iterable[Record]) -> list[Record]:
    messages: list[Record] = []
    for turn in turns:
        value = turn.get("messages")
        if isinstance(value, list):
            messages.extend(item for item in value if isinstance(item, dict))
    return messages


def _agents(turns: Iterable[Record]) -> list[str]:
    agents: list[str] = []
    for turn in turns:
        agent = turn.get("agent") or turn.get("agent_id") or turn.get("speaker")
        if agent is not None and str(agent) not in agents:
            agents.append(str(agent))
    return agents


def _round_summaries(rounds: Iterable[Record]) -> list[Record]:
    summaries: list[Record] = []
    for round_index, round_record in enumerate(rounds, start=1):
        turns = _agent_turns([round_record])
        summaries.append(
            {
                "round": _round_number(round_record, round_index),
                "agent_count": len(_agents(turns)),
                "message_count": len(_messages(turns)),
            }
        )
    return summaries


def _round_number(round_record: Record, fallback: int) -> object:
    return round_record.get("round") or round_record.get("round_index") or fallback


def _source_caveats(record: Record, affected_analysis: str) -> list[ParsedDrop]:
    caveats = [
        (
            "private_prompt_absent",
            "missing_private_prompts",
            "private_prompts",
        ),
        (
            "model_config_absent",
            "missing_model_configs",
            "model_configs",
        ),
        (
            "judge_rubric_absent",
            "missing_judge_rubric",
            "judge_rubric",
        ),
    ]
    return [
        ParsedDrop(
            loss_class=loss_class,
            reason=reason,
            dropped_field_path=field_path,
            affected_analysis=affected_analysis,
            declaration_kind="source_missing",
        )
        for loss_class, reason, field_path in caveats
        if _missing(record.get(field_path))
    ]


def _missing(value: object) -> bool:
    return value is None or value == "" or value == [] or value == {}
