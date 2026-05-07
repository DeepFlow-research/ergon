import json
from pathlib import Path

import pytest

from ergon_ingestion.models import ImportSource


VALID_RESOURCE_KINDS = {"import", "artifact", "report", "output", "search_cache", "note"}


def test_bfcl_importer_parses_jsonl_rows_with_tool_resources_and_reducers(
    tmp_path: Path,
) -> None:
    source_module = _load_bfcl_source_module()
    source_path = write_bfcl_fixture(tmp_path)
    importer = source_module.BfclImporter()
    source = ImportSource(dataset="bfcl", input_path=source_path, batch_id="bfcl-unit")

    report = importer.validate(source)
    runs = list(importer.iter_runs(source))

    assert report.ok is True
    assert report.planned_runs == 2
    assert importer.info.schema_fit_class == "row-record"
    assert importer.info.export_claim == "conditional"
    assert importer.info.default_reducers == [
        "bfcl.call_correctness",
        "bfcl.tool_call_record",
    ]
    assert [run.source_run_id for run in runs] == ["bfcl-001", "bfcl-002"]

    first = runs[0]
    assert first.schema_fit_class == "row-record"
    assert first.instance_key == "bfcl-001"
    assert first.observed_fields["prompt"] == "Call the weather tool for Paris in Celsius."
    assert first.observed_fields["category"] == "simple"
    assert first.observed_fields["correct"] is True
    assert "function_execution_trace" in first.missing_fields
    assert "function_execution_environment" in first.missing_fields

    annotations = {annotation.namespace: annotation.payload for annotation in first.annotations}
    assert annotations["bfcl.task"] == {
        "question_id": "bfcl-001",
        "prompt": "Call the weather tool for Paris in Celsius.",
        "category": "simple",
    }
    assert annotations["bfcl.tool_schema"]["tools"] == bfcl_records()[0]["tools"]
    assert annotations["bfcl.calls"]["tool_calls"] == bfcl_records()[0]["tool_calls"]
    assert annotations["bfcl.calls"]["expected_call"] == bfcl_records()[0]["expected_call"]

    resources = {resource.name: resource for resource in first.resources}
    assert {resource.kind for resource in resources.values()} <= VALID_RESOURCE_KINDS
    assert resources["source-record.json"].kind == "import"
    assert resources["tool-schema.json"].kind == "artifact"
    assert resources["model-response.json"].kind == "output"
    assert resources["expected-call.json"].kind == "report"
    assert resources["tool-schema.json"].payload == {"tools": bfcl_records()[0]["tools"]}

    reducers = {reducer.name: reducer for reducer in first.reducers}
    assert set(reducers) == {"bfcl.call_correctness", "bfcl.tool_call_record"}
    assert reducers["bfcl.call_correctness"].fields_read == [
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
    assert reducers["bfcl.call_correctness"].output == {
        "prediction": [{"name": "get_weather", "arguments": {"city": "Paris", "unit": "celsius"}}],
        "gold": {"name": "get_weather", "arguments": {"city": "Paris", "unit": "celsius"}},
        "correct": True,
        "passed": True,
        "eval_result": "passed",
        "category": "simple",
    }
    assert reducers["bfcl.tool_call_record"].fields_read == [
        "prompt",
        "functions",
        "tools",
        "model_response",
        "tool_calls",
        "expected_call",
        "ground_truth",
    ]
    assert reducers["bfcl.tool_call_record"].output["tool_schema"] == bfcl_records()[0]["tools"]
    assert (
        reducers["bfcl.tool_call_record"].output["model_response"]
        == bfcl_records()[0]["model_response"]
    )

    dropped_paths = {
        drop.dropped_field_path for reducer in first.reducers for drop in reducer.drops
    }
    assert "function_execution.trace" in dropped_paths
    assert "function_execution.environment" in dropped_paths
    assert "evaluator.judge_details" in dropped_paths

    second_call_correctness = {reducer.name: reducer for reducer in runs[1].reducers}[
        "bfcl.call_correctness"
    ]
    assert second_call_correctness.output["gold"] == bfcl_records()[1]["ground_truth"]
    assert second_call_correctness.output["passed"] is False
    assert second_call_correctness.output["correct"] is False


def test_bfcl_parser_and_reducers_preserve_function_schema_and_caveats() -> None:
    source_module = _load_bfcl_source_module()
    reducers_module = _load_bfcl_reducers_module()
    record = {
        "question_id": "bfcl-003",
        "prompt": "Schedule a meeting for tomorrow.",
        "functions": [
            {
                "name": "create_calendar_event",
                "parameters": {"type": "object", "properties": {"title": {"type": "string"}}},
            }
        ],
        "model_response": {"content": "", "tool_calls": [{"name": "create_calendar_event"}]},
        "expected_call": [{"name": "create_calendar_event", "arguments": {"title": "meeting"}}],
        "category": "parallel",
        "eval_result": {"passed": False, "reason": "missing argument"},
    }

    run = source_module.parse_bfcl_record(record)
    correctness = reducers_module.call_correctness_reducer(record)
    call_record = reducers_module.tool_call_record_reducer(record)

    assert run.source_run_id == "bfcl-003"
    assert run.schema_fit_class == "row-record"
    assert run.observed_fields["functions"] == record["functions"]
    assert one_resource_named(run.resources, "tool-schema.json").payload == {
        "functions": record["functions"]
    }

    assert correctness.name == "bfcl.call_correctness"
    assert correctness.output["prediction"] == [{"name": "create_calendar_event"}]
    assert correctness.output["gold"] == record["expected_call"]
    assert correctness.output["passed"] is False
    assert correctness.output["correct"] is None
    assert correctness.fields_read

    assert call_record.name == "bfcl.tool_call_record"
    assert call_record.output["prompt"] == "Schedule a meeting for tomorrow."
    assert call_record.output["tool_schema"] == record["functions"]
    assert call_record.output["expected_call"] == record["expected_call"]
    assert call_record.fields_read

    drop_reasons = {drop.reason for drop in correctness.drops + call_record.drops}
    assert "function_execution_trace_unavailable_in_row_record" in drop_reasons
    assert "function_execution_environment_unavailable_in_row_record" in drop_reasons
    assert "judge_details_unavailable_or_dataset_dependent" in drop_reasons


def write_bfcl_fixture(tmp_path: Path) -> Path:
    source_path = tmp_path / "bfcl.jsonl"
    source_path.write_text("\n".join(json.dumps(record) for record in bfcl_records()) + "\n")
    return source_path


def bfcl_records() -> list[dict[str, object]]:
    return [
        {
            "id": "bfcl-001",
            "prompt": "Call the weather tool for Paris in Celsius.",
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "get_weather",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "city": {"type": "string"},
                                "unit": {"type": "string"},
                            },
                        },
                    },
                }
            ],
            "model_response": {"role": "assistant", "content": "", "tool_calls": ["call-1"]},
            "tool_calls": [
                {"name": "get_weather", "arguments": {"city": "Paris", "unit": "celsius"}}
            ],
            "expected_call": {
                "name": "get_weather",
                "arguments": {"city": "Paris", "unit": "celsius"},
            },
            "category": "simple",
            "correct": True,
            "eval_result": "passed",
        },
        {
            "question_id": "bfcl-002",
            "prompt": "Book a hotel in Kyoto.",
            "functions": [{"name": "book_hotel", "parameters": {"type": "object"}}],
            "model_response": "I cannot complete that booking.",
            "ground_truth": [{"name": "book_hotel", "arguments": {"city": "Kyoto"}}],
            "category": "irrelevance",
            "pass": False,
            "eval_result": {"passed": False, "reason": "no function call"},
        },
    ]


def one_resource_named(resources, name: str):
    matches = [resource for resource in resources if resource.name == name]
    assert len(matches) == 1
    return matches[0]


def _load_bfcl_source_module():
    try:
        from ergon_ingestion.sources import bfcl
    except ModuleNotFoundError as exc:
        pytest.fail(f"BFCL source parser is not implemented: {exc}")
    return bfcl


def _load_bfcl_reducers_module():
    try:
        from ergon_ingestion.reducers import bfcl
    except ModuleNotFoundError as exc:
        pytest.fail(f"BFCL reducers are not implemented: {exc}")
    return bfcl
