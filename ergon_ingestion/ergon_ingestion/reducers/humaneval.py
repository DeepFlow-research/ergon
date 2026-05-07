"""Reducer helpers for HumanEval row-record imports."""

from ergon_ingestion.models import ParsedDrop, ParsedReducer

ORIGINAL_PASS_FIELDS = ["original_passed", "driver_results.original.passed"]
EVALPLUS_PASS_FIELDS = ["evalplus_passed", "driver_results.evalplus.passed"]


def original_pass_reducer(record: dict[str, object]) -> ParsedReducer:
    """Read the original HumanEval test-suite pass/fail result."""
    return ParsedReducer(
        name="humaneval.original_pass",
        kind="original",
        output={"passed": _passed_result(record, flat_key="original_passed", variants=("original", "base"))},
        implementation_ref="ergon_ingestion.reducers.humaneval.original_pass_reducer",
        fields_read=ORIGINAL_PASS_FIELDS,
        drops=[
            ParsedDrop(
                loss_class="unavailable_source_field",
                reason="hidden_original_tests_unavailable_in_row_record",
                dropped_field_path="original.hidden_tests",
                affected_analysis="humaneval.original_pass",
                declaration_kind="source_missing",
            )
        ],
    )


def evalplus_pass_reducer(record: dict[str, object]) -> ParsedReducer:
    """Read EvalPlus or driver variant pass/fail while declaring suite escalation caveats."""
    return ParsedReducer(
        name="humaneval.evalplus_pass",
        kind="regrade",
        output={
            "passed": _passed_result(
                record,
                flat_key="evalplus_passed",
                variants=("evalplus", "eval_plus", "plus"),
            )
        },
        implementation_ref="ergon_ingestion.reducers.humaneval.evalplus_pass_reducer",
        fields_read=EVALPLUS_PASS_FIELDS,
        drops=[
            ParsedDrop(
                loss_class="test_suite_escalation",
                reason="evalplus_is_test_suite_escalation_and_reporting_variance",
                dropped_field_path="evalplus.test_suite_delta",
                affected_analysis="humaneval.evalplus_pass",
                evidence={
                    "caveat": (
                        "EvalPlus/driver variants are not only reporting variance; they may add or "
                        "change tests relative to the original HumanEval suite."
                    )
                },
            ),
            ParsedDrop(
                loss_class="unavailable_source_field",
                reason="driver_execution_trace_unavailable_in_row_record",
                dropped_field_path="driver.execution_trace",
                affected_analysis="humaneval.evalplus_pass",
                declaration_kind="source_missing",
            ),
        ],
    )


def default_reducers(record: dict[str, object]) -> list[ParsedReducer]:
    return [original_pass_reducer(record), evalplus_pass_reducer(record)]


def _passed_result(
    record: dict[str, object],
    *,
    flat_key: str,
    variants: tuple[str, ...],
) -> object:
    if flat_key in record:
        return record[flat_key]

    driver_results = record.get("driver_results")
    if not isinstance(driver_results, dict):
        return None

    for variant in variants:
        result = driver_results.get(variant)
        if isinstance(result, dict) and "passed" in result:
            return result["passed"]
        if isinstance(result, bool):
            return result
    return None
