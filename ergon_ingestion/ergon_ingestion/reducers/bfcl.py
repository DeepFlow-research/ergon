"""Reducer helpers for BFCL row-record imports."""

from ergon_ingestion.models import ParsedDrop, ParsedReducer

Record = dict[str, object]

CALL_CORRECTNESS_FIELDS = [
    "model_response",
    "tool_calls",
    "expected_call",
    "ground_truth",
    "correct",
    "pass",
    "passed",
    "eval_result",
    "category",
]
TOOL_CALL_RECORD_FIELDS = [
    "prompt",
    "functions",
    "tools",
    "model_response",
    "tool_calls",
    "expected_call",
    "ground_truth",
]


def call_correctness_reducer(record: Record) -> ParsedReducer:
    """Read BFCL prediction/gold correctness fields while declaring row-record caveats."""

    correct = _explicit_correct(record)
    passed = _passed_result(record)
    return ParsedReducer(
        name="bfcl.call_correctness",
        kind="original",
        output={
            "prediction": _prediction(record),
            "gold": _first_present(record, ["expected_call", "ground_truth"]),
            "correct": correct,
            "passed": passed,
            "eval_result": record.get("eval_result"),
            "category": record.get("category"),
        },
        implementation_ref="ergon_ingestion.reducers.bfcl.call_correctness_reducer",
        fields_read=CALL_CORRECTNESS_FIELDS,
        drops=_bfcl_row_record_drops("bfcl.call_correctness"),
    )


def tool_call_record_reducer(record: Record) -> ParsedReducer:
    """Expose BFCL prompts, tool schemas, predictions, and gold calls as a diagnostic record."""

    return ParsedReducer(
        name="bfcl.tool_call_record",
        kind="diagnostic",
        output={
            "prompt": _first_present(record, ["prompt", "question"]),
            "tool_schema": _first_present(record, ["tools", "functions"]),
            "model_response": record.get("model_response"),
            "tool_calls": _prediction(record),
            "expected_call": _first_present(record, ["expected_call", "ground_truth"]),
        },
        implementation_ref="ergon_ingestion.reducers.bfcl.tool_call_record_reducer",
        fields_read=TOOL_CALL_RECORD_FIELDS,
        drops=_bfcl_row_record_drops("bfcl.tool_call_record"),
    )


def default_reducers(record: Record) -> list[ParsedReducer]:
    return [call_correctness_reducer(record), tool_call_record_reducer(record)]


def _bfcl_row_record_drops(affected_analysis: str) -> list[ParsedDrop]:
    return [
        ParsedDrop(
            loss_class="unavailable_source_field",
            reason="function_execution_trace_unavailable_in_row_record",
            dropped_field_path="function_execution.trace",
            affected_analysis=affected_analysis,
            declaration_kind="source_missing",
        ),
        ParsedDrop(
            loss_class="unavailable_source_field",
            reason="function_execution_environment_unavailable_in_row_record",
            dropped_field_path="function_execution.environment",
            affected_analysis=affected_analysis,
            declaration_kind="source_missing",
        ),
        ParsedDrop(
            loss_class="evaluator_caveat",
            reason="judge_details_unavailable_or_dataset_dependent",
            dropped_field_path="evaluator.judge_details",
            affected_analysis=affected_analysis,
            declaration_kind="source_missing",
            evidence={
                "note": (
                    "BFCL row records usually expose final pass/correct fields, not the full "
                    "judge prompt, scoring trace, or tool execution transcript."
                )
            },
        ),
    ]


def _prediction(record: Record) -> object | None:
    if "tool_calls" in record:
        return record["tool_calls"]
    model_response = record.get("model_response")
    if isinstance(model_response, dict):
        return model_response.get("tool_calls")
    return model_response


def _passed_result(record: Record) -> bool | None:
    for key in ("passed", "pass"):
        value = _bool_or_none(record.get(key))
        if value is not None:
            return value
    eval_result = record.get("eval_result")
    if isinstance(eval_result, dict):
        return _bool_or_none(eval_result.get("passed"))
    if isinstance(eval_result, str):
        normalized = eval_result.strip().lower()
        if normalized in {"pass", "passed", "correct", "true"}:
            return True
        if normalized in {"fail", "failed", "incorrect", "false"}:
            return False
    return _bool_or_none(record.get("correct"))


def _explicit_correct(record: Record) -> bool | None:
    correct = _bool_or_none(record.get("correct"))
    if correct is not None:
        return correct
    for key in ("passed", "pass"):
        value = _bool_or_none(record.get(key))
        if value is not None:
            return value
    return None


def _first_present(record: Record, keys: list[str]) -> object | None:
    for key in keys:
        if key in record:
            return record[key]
    return None


def _bool_or_none(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    return None
