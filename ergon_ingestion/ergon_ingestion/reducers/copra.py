"""Reducer helpers for COPRA theorem-result logs."""

from ergon_ingestion.models import ParsedDrop, ParsedReducer

PROVED_FAILED_FIELDS = ["SearchResult", "outcome", "Proof"]
REALISED_SEARCH_COST_FIELDS = ["SearchResult", "outcome", "StepsUsed", "elapsed_seconds"]


def proved_failed_reducer(record: dict[str, object]) -> ParsedReducer:
    """Recover the theorem-level proved/failed label from COPRA result fields."""
    search_result = _string_or_none(record.get("SearchResult"))
    outcome = _normalised_outcome(record)
    return ParsedReducer(
        name="copra.proved_failed",
        kind="original",
        output={
            "proved": _is_proved(record),
            "outcome": outcome,
            "search_result": search_result,
        },
        implementation_ref="ergon_ingestion.reducers.copra.proved_failed_reducer",
        fields_read=PROVED_FAILED_FIELDS,
        drops=_unavailable_search_detail_drops("copra.proved_failed"),
    )


def realised_search_cost_reducer(record: dict[str, object]) -> ParsedReducer:
    """Recover realized search effort observed in COPRA logs."""
    return ParsedReducer(
        name="copra.realised_search_cost",
        kind="recovered",
        output={
            "steps_used": record.get("StepsUsed"),
            "elapsed_seconds": record.get("elapsed_seconds"),
            "proved": _is_proved(record),
        },
        implementation_ref="ergon_ingestion.reducers.copra.realised_search_cost_reducer",
        fields_read=REALISED_SEARCH_COST_FIELDS,
        drops=_unavailable_search_detail_drops("copra.realised_search_cost"),
    )


def _is_proved(record: dict[str, object]) -> bool:
    search_result = _string_or_none(record.get("SearchResult"))
    outcome = _normalised_outcome(record)
    return search_result in {"SUCCESS", "PROVED"} or outcome == "proved"


def _normalised_outcome(record: dict[str, object]) -> str:
    outcome = _string_or_none(record.get("outcome"))
    if outcome:
        lowered = outcome.lower()
        if lowered in {"proved", "success", "successful"}:
            return "proved"
        if lowered in {"failed", "failure", "unproved"}:
            return "failed"
        return lowered
    return "proved" if _string_or_none(record.get("SearchResult")) in {"SUCCESS", "PROVED"} else "failed"


def _unavailable_search_detail_drops(affected_analysis: str) -> list[ParsedDrop]:
    return [
        ParsedDrop(
            loss_class="unavailable_source_field",
            reason="unavailable_in_source",
            dropped_field_path="failed_proof_states",
            affected_analysis=affected_analysis,
            declaration_kind="source_missing",
        ),
        ParsedDrop(
            loss_class="unavailable_source_field",
            reason="unavailable_in_source",
            dropped_field_path="failed_tactic_branches",
            affected_analysis=affected_analysis,
            declaration_kind="source_missing",
        ),
    ]


def _string_or_none(value: object) -> str | None:
    if value is None:
        return None
    return str(value)
