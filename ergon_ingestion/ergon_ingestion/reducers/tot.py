"""Reducers for Tree-of-Thought trace imports."""

from typing import Any

from ergon_ingestion.models import ParsedDrop, ParsedReducer

HIDDEN_INTERNAL_FIELDS = (
    "evaluator.value_estimates",
    "pruning.branch_scores",
    "pruning.hidden_thresholds",
)

GAME24_MISSING_FIELDS = (
    "steps[].branch_id",
    "evaluator.internal_value_model",
    "evaluator.prompt_transcripts",
)

SEARCH_EFFICIENCY_FIELDS_READ = [
    "actions",
    "states",
    "search.visited_states",
    "search.max_depth",
    "search.backtracks",
    "search.coverage",
    "final_reward",
]


def final_reward(record: dict[str, Any]) -> ParsedReducer:
    """Recover the final reward reported by a ToT trace."""
    return ParsedReducer(
        name="tot.final_reward",
        kind="original",
        output={"final_reward": record.get("final_reward")},
        implementation_ref="ergon_ingestion.reducers.tot.final_reward",
        fields_read=["final_reward"],
        drops=_missing_internal_drops(record, affected_analysis="reward-attribution"),
    )


def search_efficiency(record: dict[str, Any]) -> ParsedReducer:
    """Summarize search shape fields used by the ToT crossword analysis."""
    output = search_efficiency_output(record)
    return ParsedReducer(
        name="tot.search_efficiency",
        kind="recovered",
        output=output,
        implementation_ref="ergon_ingestion.reducers.tot.search_efficiency",
        fields_read=SEARCH_EFFICIENCY_FIELDS_READ,
        drops=_missing_internal_drops(record, affected_analysis="search-shape"),
    )


def search_efficiency_output(record: dict[str, Any]) -> dict[str, Any]:
    actions = _list(record.get("actions"))
    states = _list(record.get("states"))
    search = _dict(record.get("search"))
    visited_states = int(search.get("visited_states") or len(states))
    final = record.get("final_reward")
    reward_per_state = None
    if isinstance(final, int | float) and visited_states:
        reward_per_state = final / visited_states
    return {
        "visited_states": visited_states,
        "action_count": len(actions),
        "unique_atomic_actions": len({str(action) for action in actions}),
        "max_depth": int(search.get("max_depth") or _max_depth(states)),
        "backtracks": int(search.get("backtracks") or _count_backtracks(actions)),
        "coverage": search.get("coverage"),
        "reward_per_visited_state": reward_per_state,
    }


def game24_final_answer(record: dict[str, Any]) -> ParsedReducer:
    """Recover Game24 final answer and source-observed correctness."""
    return ParsedReducer(
        name="tot.game24_final_answer",
        kind="original",
        output={
            "numbers": record.get("numbers"),
            "final_answer": record.get("final_answer"),
            "final_reward": record.get("final_reward"),
            "source_correct": _game24_source_correct(record),
        },
        implementation_ref="ergon_ingestion.reducers.tot.game24_final_answer",
        fields_read=["numbers", "final_answer", "final_reward", "infos", "correctness"],
        drops=_game24_trace_drops(record, affected_analysis="final-answer"),
    )


def game24_value_trace(record: dict[str, Any]) -> ParsedReducer:
    """Summarize Game24 branch/value trace evidence preserved by the source."""
    infos = _game24_infos(record)
    return ParsedReducer(
        name="tot.game24_value_trace",
        kind="recovered",
        output={
            "step_count": len(_list(record.get("steps"))),
            "action_count": len(_list(record.get("actions"))),
            "value_count": len(_list(record.get("values"))),
            "info_count": len(infos),
            "values": [_game24_value(value) for value in _list(record.get("values"))],
            "source_correct_count": sum(1 for info in infos if info.get("correct") is True),
        },
        implementation_ref="ergon_ingestion.reducers.tot.game24_value_trace",
        fields_read=["steps", "actions", "values", "infos", "correctness"],
        drops=_game24_trace_drops(record, affected_analysis="value-trace"),
    )


def missing_game24_fields(record: dict[str, Any]) -> list[str]:
    missing = [
        field
        for field in GAME24_MISSING_FIELDS
        if field != "steps[].branch_id" and _lookup_path(record, field) is None
    ]
    if not _game24_has_branch_ids(record):
        missing.insert(0, "steps[].branch_id")
    return missing


def missing_internal_fields(record: dict[str, Any]) -> list[str]:
    return [field for field in HIDDEN_INTERNAL_FIELDS if _lookup_path(record, field) is None]


def _missing_internal_drops(record: dict[str, Any], *, affected_analysis: str) -> list[ParsedDrop]:
    return [
        ParsedDrop(
            loss_class="unavailable_source_field",
            reason="hidden ToT evaluator/pruning internals are absent from public DFS trace",
            dropped_field_path=field,
            affected_analysis=affected_analysis,
            declaration_kind="source_missing",
        )
        for field in missing_internal_fields(record)
    ]


def _game24_trace_drops(record: dict[str, Any], *, affected_analysis: str) -> list[ParsedDrop]:
    drops = (
        [
            ParsedDrop(
                loss_class="unavailable_source_field",
                reason="Game24 trace does not expose stable branch identifiers for implicit ToT branches",
                dropped_field_path="steps[].branch_id",
                affected_analysis=affected_analysis,
                declaration_kind="source_missing",
            )
        ]
        if not _game24_has_branch_ids(record)
        else []
    )
    drops.extend(
        ParsedDrop(
            loss_class="unavailable_source_field",
            reason="Game24 public trace omits evaluator prompt/value-model internals",
            dropped_field_path=field,
            affected_analysis=affected_analysis,
            declaration_kind="source_missing",
        )
        for field in ("evaluator.internal_value_model", "evaluator.prompt_transcripts")
        if _lookup_path(record, field) is None
    )
    if _game24_infos(record):
        drops.append(
            ParsedDrop(
                loss_class="source_semantics_caveat",
                reason="correctness is preserved from source infos/correctness fields, not recomputed",
                dropped_field_path="infos[].correct",
                affected_analysis=affected_analysis,
                declaration_kind="author_declared",
            )
        )
    return drops


def _game24_has_branch_ids(record: dict[str, Any]) -> bool:
    steps = _list(record.get("steps"))
    return bool(steps) and all(isinstance(step, dict) and step.get("branch_id") for step in steps)


def _game24_source_correct(record: dict[str, Any]) -> bool | None:
    infos = _game24_infos(record)
    if infos:
        return infos[-1].get("correct")
    final_reward = record.get("final_reward")
    if isinstance(final_reward, int | float):
        return final_reward > 0
    return None


def _game24_infos(record: dict[str, Any]) -> list[dict[str, Any]]:
    infos = [info for info in _list(record.get("infos")) if isinstance(info, dict)]
    if infos:
        return infos
    correctness = record.get("correctness")
    if isinstance(correctness, list):
        return [{"correct": value} for value in correctness]
    return [
        {"correct": step["correct"]}
        for step in _list(record.get("steps"))
        if isinstance(step, dict) and "correct" in step
    ]


def _game24_value(value: Any) -> Any:
    if isinstance(value, dict) and "value" in value:
        return value["value"]
    return value


def _lookup_path(record: dict[str, Any], path: str) -> Any:
    current: Any = record
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _max_depth(states: list[Any]) -> int:
    depths = [state.get("depth", 0) for state in states if isinstance(state, dict)]
    return int(max(depths, default=0))


def _count_backtracks(actions: list[Any]) -> int:
    return sum(1 for action in actions if "backtrack" in str(action).lower())
