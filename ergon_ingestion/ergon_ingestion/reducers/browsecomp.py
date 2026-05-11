"""Reducers for BrowseComp answer-centric row records."""

import re

from ergon_ingestion.models import ParsedDrop, ParsedReducer

Record = dict[str, object]

EXACT_MATCH_FIELDS = ["gold_answer", "predicted_answer"]
LLM_JUDGE_FIELDS = ["judge_result", "judge_explanation"]


def exact_match_reducer(record: Record) -> ParsedReducer:
    """Compare gold and predicted answers with simple case/whitespace normalization."""

    gold = _string_or_none(record.get("gold_answer"))
    predicted = _string_or_none(record.get("predicted_answer"))
    normalized_gold = _normalize_answer(gold)
    normalized_predicted = _normalize_answer(predicted)
    exact_match = (
        None
        if normalized_gold is None or normalized_predicted is None
        else normalized_gold == normalized_predicted
    )

    return ParsedReducer(
        name="browsecomp.exact_match",
        kind="original",
        output={
            "exact_match": exact_match,
            "normalized_gold_answer": normalized_gold,
            "normalized_predicted_answer": normalized_predicted,
        },
        implementation_ref="ergon_ingestion.reducers.browsecomp.exact_match_reducer",
        fields_read=EXACT_MATCH_FIELDS,
        drops=_missing_browsing_trace_drops(record),
    )


def llm_judge_reducer(record: Record) -> ParsedReducer:
    """Preserve the source BrowseComp judge result and explanation."""

    return ParsedReducer(
        name="browsecomp.llm_judge",
        kind="original",
        output={
            "judge_result": record.get("judge_result"),
            "judge_explanation": record.get("judge_explanation"),
        },
        implementation_ref="ergon_ingestion.reducers.browsecomp.llm_judge_reducer",
        fields_read=LLM_JUDGE_FIELDS,
        drops=[_non_replayable_judge_drop(), *_missing_browsing_trace_drops(record)],
    )


def default_reducers(record: Record) -> list[ParsedReducer]:
    return [exact_match_reducer(record), llm_judge_reducer(record)]


def _normalize_answer(value: str | None) -> str | None:
    if value is None:
        return None
    return re.sub(r"\s+", " ", value.strip().casefold())


def _string_or_none(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _missing_browsing_trace_drops(record: Record) -> list[ParsedDrop]:
    if "browsing_trace" in record or "browser_trace" in record:
        return []
    return [
        ParsedDrop(
            loss_class="unavailable_source_field",
            reason="source_row_does_not_include_browsing_trace",
            dropped_field_path="browsing_trace",
            affected_analysis="browsecomp.answer_verification_from_trace",
            declaration_kind="source_missing",
        )
    ]


def _non_replayable_judge_drop() -> ParsedDrop:
    return ParsedDrop(
        loss_class="non_replayable_stochastic_judge",
        reason="source_llm_judge_is_stochastic_and_not_replayable_without_original_judge_context",
        dropped_field_path="judge.replay_context",
        affected_analysis="browsecomp.llm_judge",
        declaration_kind="source_missing",
    )
