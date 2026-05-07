"""Reducer helpers for MATH fixed-completion row records."""

from ergon_ingestion.models import ParsedDrop, ParsedReducer

Record = dict[str, object]

EXTRACTED_ACCURACY_FIELDS = [
    "solution",
    "gold_answer",
    "completion",
    "model_answer",
    "extracted_answer",
    "correct",
    "passed",
    "llm_judge",
    "judge",
]
NORMALIZATION_CONVENTION_FIELDS = [
    "boxed",
    "normalization_mode",
    "convention",
    "extracted_answer",
]


def extracted_accuracy_reducer(record: Record) -> ParsedReducer:
    """Preserve MATH extracted-answer labels without regrading completions."""

    return ParsedReducer(
        name="math.extracted_accuracy",
        kind="original",
        output={
            "gold_answer": _first_present(record, ["gold_answer", "solution"]),
            "completion": _first_present(record, ["completion", "model_answer"]),
            "extracted_answer": record.get("extracted_answer"),
            "correct": _first_present(record, ["correct", "passed"]),
            "llm_judge": _first_present(record, ["llm_judge", "judge"]),
        },
        implementation_ref="ergon_ingestion.reducers.math.extracted_accuracy_reducer",
        fields_read=EXTRACTED_ACCURACY_FIELDS,
        drops=_missing_judge_drops(record, "math.extracted_accuracy"),
    )


def normalization_convention_reducer(record: Record) -> ParsedReducer:
    """Declare answer extraction and normalization conventions used by a MATH row."""

    return ParsedReducer(
        name="math.normalization_convention",
        kind="diagnostic",
        output={
            "boxed": record.get("boxed"),
            "normalization_mode": record.get("normalization_mode"),
            "convention": record.get("convention"),
            "extracted_answer": record.get("extracted_answer"),
        },
        implementation_ref="ergon_ingestion.reducers.math.normalization_convention_reducer",
        fields_read=NORMALIZATION_CONVENTION_FIELDS,
        drops=_missing_judge_drops(record, "math.normalization_convention"),
    )


def default_reducers(record: Record) -> list[ParsedReducer]:
    return [extracted_accuracy_reducer(record), normalization_convention_reducer(record)]


def missing_judge_fields(record: Record) -> list[str]:
    if _first_present(record, ["llm_judge", "judge"]) is None:
        return ["llm_judge.regrade"]
    return []


def _missing_judge_drops(record: Record, affected_analysis: str) -> list[ParsedDrop]:
    return [
        ParsedDrop(
            loss_class="calibration_caveat",
            reason="missing_llm_judge_regrading_context",
            dropped_field_path=field,
            affected_analysis=affected_analysis,
            declaration_kind="source_missing",
            evidence={
                "note": "MATH rows preserve fixed completions and extracted answers, but do not "
                "include an LLM judge or regrading trace.",
            },
        )
        for field in missing_judge_fields(record)
    ]


def _first_present(record: Record, keys: list[str]) -> object | None:
    for key in keys:
        if key in record:
            return record[key]
    return None
