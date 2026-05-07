"""Reducer helpers for MMLU row-record imports."""

from ergon_ingestion.models import ParsedDrop, ParsedReducer

ANSWER_ACCURACY_FIELDS = [
    "predicted",
    "predicted_answer",
    "gold",
    "answer",
    "choice_logprobs",
    "logprobs",
    "details",
]
PROMPT_EXTRACTION_FIELDS = [
    "prompt_template",
    "template",
    "extraction_mode",
    "extraction",
    "full_prompt",
    "prompt",
    "generation",
    "full_generation",
]


def answer_accuracy_reducer(row: dict[str, object]) -> ParsedReducer:
    """Recover per-row MMLU answer correctness from gold/predicted answer fields."""
    predicted = normalized_answer(_first_present(row, ["predicted", "predicted_answer", "prediction"]))
    gold = normalized_answer(_first_present(row, ["gold", "answer", "target"]))
    return ParsedReducer(
        name="mmlu.answer_accuracy",
        kind="original",
        output={
            "correct": predicted == gold if predicted is not None and gold is not None else None,
            "predicted_answer": predicted,
            "gold_answer": gold,
            "subject": _string_or_none(row.get("subject")),
            "has_choice_logprobs": _has_choice_logprobs(row),
        },
        implementation_ref="ergon_ingestion.reducers.mmlu.answer_accuracy_reducer",
        fields_read=ANSWER_ACCURACY_FIELDS,
        drops=_missing_full_context_drops(row, "mmlu.answer_accuracy"),
    )


def prompt_extraction_convention_reducer(row: dict[str, object]) -> ParsedReducer:
    """Declare the prompt template and answer extraction convention observed in a row."""
    return ParsedReducer(
        name="mmlu.prompt_extraction_convention",
        kind="diagnostic",
        output={
            "prompt_template": _string_or_none(
                _first_present(row, ["prompt_template", "template"])
            ),
            "extraction_mode": _extraction_mode(row),
            "has_full_prompt": _has_full_prompt(row),
            "has_full_generation": _has_full_generation(row),
        },
        implementation_ref=(
            "ergon_ingestion.reducers.mmlu.prompt_extraction_convention_reducer"
        ),
        fields_read=PROMPT_EXTRACTION_FIELDS,
        drops=_missing_full_context_drops(row, "mmlu.prompt_extraction_convention"),
    )


def normalized_answer(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, int):
        return chr(ord("A") + value)
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        return chr(ord("A") + int(text))
    return text[0].upper()


def missing_full_context_fields(row: dict[str, object]) -> list[str]:
    missing = []
    if not _has_full_generation(row):
        missing.append("full_generation")
    if not _has_full_prompt(row):
        missing.append("full_prompt")
    return missing


def _missing_full_context_drops(
    row: dict[str, object], affected_analysis: str
) -> list[ParsedDrop]:
    return [
        ParsedDrop(
            loss_class="unavailable_source_field",
            reason="unavailable_in_source",
            dropped_field_path=field,
            affected_analysis=affected_analysis,
            declaration_kind="source_missing",
        )
        for field in missing_full_context_fields(row)
    ]


def _has_choice_logprobs(row: dict[str, object]) -> bool:
    return row.get("choice_logprobs") is not None or row.get("logprobs") is not None


def _has_full_generation(row: dict[str, object]) -> bool:
    return _has_non_empty(row, ["full_generation", "generation"])


def _has_full_prompt(row: dict[str, object]) -> bool:
    return _has_non_empty(row, ["full_prompt", "prompt"])


def _has_non_empty(row: dict[str, object], keys: list[str]) -> bool:
    value = _first_present(row, keys)
    return value is not None and str(value).strip() != ""


def _extraction_mode(row: dict[str, object]) -> str | None:
    explicit = _string_or_none(row.get("extraction_mode"))
    if explicit:
        return explicit
    extraction = row.get("extraction")
    if isinstance(extraction, dict):
        return _string_or_none(extraction.get("mode"))
    return _string_or_none(extraction)


def _first_present(row: dict[str, object], keys: list[str]) -> object | None:
    for key in keys:
        if key in row:
            return row[key]
    return None


def _string_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
