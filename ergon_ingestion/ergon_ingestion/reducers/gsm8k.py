"""Reducer helpers for GSM8K fixed-completion row records."""

import re

from ergon_ingestion.models import ParsedDrop, ParsedReducer

Record = dict[str, object]

EXTRACTED_ACCURACY_FIELDS = [
    "gold_answer",
    "answer",
    "completion",
    "extracted_answer",
    "correct",
    "passed",
]
ANSWER_FORMAT_CONVENTION_FIELDS = [
    "convention",
    "mode",
    "extractor_mode",
    "completion",
    "gold_answer",
    "answer",
    "extracted_answer",
]

_BOXED_PATTERN = re.compile(r"\\boxed\{([^}]*)\}")
_NUMBER_PATTERN = re.compile(r"-?\d+(?:,\d{3})*(?:\.\d+)?(?:/\d+)?")


def extracted_accuracy_reducer(record: Record) -> ParsedReducer:
    """Compute GSM8K extracted-answer accuracy after lightweight answer normalization."""

    gold = normalized_answer(_first_present(record, ["gold_answer", "answer"]))
    extracted = normalized_answer(record.get("extracted_answer"))
    correct = _bool_or_none(record.get("correct"))
    if correct is None and gold is not None and extracted is not None:
        correct = gold == extracted
    passed = _bool_or_none(record.get("passed"))
    if passed is None:
        passed = correct
    return ParsedReducer(
        name="gsm8k.extracted_accuracy",
        kind="original",
        output={
            "gold_answer": gold,
            "extracted_answer": extracted,
            "correct": correct,
            "passed": passed,
            "has_completion": _has_non_empty(record.get("completion")),
        },
        implementation_ref="ergon_ingestion.reducers.gsm8k.extracted_accuracy_reducer",
        fields_read=EXTRACTED_ACCURACY_FIELDS,
        drops=_answer_format_drops("gsm8k.extracted_accuracy"),
    )


def answer_format_convention_reducer(record: Record) -> ParsedReducer:
    """Expose GSM8K answer formatting convention fields and related caveats."""

    completion = str(record.get("completion") or "")
    gold_answer = str(_first_present(record, ["gold_answer", "answer"]) or "")
    combined_answer_text = f"{gold_answer}\n{completion}"
    return ParsedReducer(
        name="gsm8k.answer_format_convention",
        kind="diagnostic",
        output={
            "convention": _string_or_none(record.get("convention")),
            "mode": _string_or_none(record.get("mode")),
            "extractor_mode": _string_or_none(record.get("extractor_mode")),
            "has_hash_delimiter": "####" in combined_answer_text,
            "has_boxed_answer": "\\boxed{" in combined_answer_text,
            "weak_model_formatting": "weak" in str(record.get("mode") or "").lower(),
        },
        implementation_ref="ergon_ingestion.reducers.gsm8k.answer_format_convention_reducer",
        fields_read=ANSWER_FORMAT_CONVENTION_FIELDS,
        drops=_answer_format_drops("gsm8k.answer_format_convention"),
    )


def default_reducers(record: Record) -> list[ParsedReducer]:
    return [extracted_accuracy_reducer(record), answer_format_convention_reducer(record)]


def normalized_answer(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if "####" in text:
        text = text.rsplit("####", maxsplit=1)[-1].strip()
    boxed_match = _BOXED_PATTERN.search(text)
    if boxed_match:
        text = boxed_match.group(1).strip()
    number_matches = _NUMBER_PATTERN.findall(text)
    if number_matches:
        return number_matches[-1].replace(",", "")
    return text


def _answer_format_drops(affected_analysis: str) -> list[ParsedDrop]:
    return [
        ParsedDrop(
            loss_class="normalization_caveat",
            reason="answer_format_convention_dependent",
            dropped_field_path="answer.format_convention",
            affected_analysis=affected_analysis,
            declaration_kind="author_declared",
            evidence={
                "note": "GSM8K correctness depends on source conventions such as ####, boxed "
                "answers, and weak-model final-number formatting.",
            },
        ),
        ParsedDrop(
            loss_class="normalization_caveat",
            reason="answer_normalization_provenance_unavailable",
            dropped_field_path="answer.normalization_provenance",
            affected_analysis=affected_analysis,
            declaration_kind="source_missing",
        ),
    ]


def _first_present(record: Record, keys: list[str]) -> object | None:
    for key in keys:
        if key in record:
            return record[key]
    return None


def _bool_or_none(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


def _has_non_empty(value: object) -> bool:
    return value is not None and str(value).strip() != ""


def _string_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
