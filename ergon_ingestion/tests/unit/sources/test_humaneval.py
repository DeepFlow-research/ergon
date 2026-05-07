import json
from pathlib import Path

from ergon_ingestion.models import ImportSource
from ergon_ingestion.reducers.humaneval import evalplus_pass_reducer, original_pass_reducer
from ergon_ingestion.sources.humaneval import HumanEvalImporter, parse_humaneval_record


VALID_RESOURCE_KINDS = {"import", "artifact", "report", "output", "search_cache", "note"}


def test_humaneval_importer_parses_jsonl_rows_with_code_resources_and_reducers(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "humaneval.jsonl"
    rows = [
        {
            "task_id": "HumanEval/0",
            "prompt": "def add(a, b):\n",
            "completion": "    return a + b\n",
            "original_passed": True,
            "evalplus_passed": False,
        },
        {
            "task_id": "HumanEval/1",
            "prompt": "def is_odd(n):\n",
            "code": "def is_odd(n):\n    return n % 2 == 1\n",
            "driver_results": {
                "original": {"passed": False},
                "evalplus": {"passed": False, "failed_tests": 2},
            },
        },
    ]
    source_path.write_text("\n".join(json.dumps(row) for row in rows))

    importer = HumanEvalImporter()
    source = ImportSource(dataset="humaneval", input_path=source_path, batch_id="humaneval-unit")
    report = importer.validate(source)
    runs = list(importer.iter_runs(source))

    assert report.ok is True
    assert report.planned_runs == 2
    assert [run.source_run_id for run in runs] == ["HumanEval/0", "HumanEval/1"]
    assert all(run.schema_fit_class == "row-record" for run in runs)
    assert runs[0].observed_fields["prompt"] == "def add(a, b):\n"
    assert runs[0].observed_fields["completion"] == "    return a + b\n"
    assert runs[1].observed_fields["code"] == rows[1]["code"]

    code_resource = one_resource_named(runs[0].resources, "completion.py")
    assert code_resource.kind in VALID_RESOURCE_KINDS
    assert code_resource.kind == "output"
    assert code_resource.payload == "    return a + b\n"

    reducers = {reducer.name: reducer for reducer in runs[0].reducers}
    assert set(reducers) == {"humaneval.original_pass", "humaneval.evalplus_pass"}
    assert reducers["humaneval.original_pass"].fields_read == [
        "original_passed",
        "driver_results.original.passed",
    ]
    assert reducers["humaneval.original_pass"].output == {"passed": True}
    assert reducers["humaneval.evalplus_pass"].fields_read == [
        "evalplus_passed",
        "driver_results.evalplus.passed",
    ]
    assert reducers["humaneval.evalplus_pass"].output == {"passed": False}

    drop_reasons = {drop.reason for reducer in runs[0].reducers for drop in reducer.drops}
    assert "evalplus_is_test_suite_escalation_and_reporting_variance" in drop_reasons


def test_humaneval_parser_and_reducers_read_driver_variant_results() -> None:
    record = {
        "task_id": "HumanEval/2",
        "prompt": "def negate(x):\n",
        "completion": "    return not x\n",
        "driver_results": {
            "original": {"passed": True, "duration_seconds": 0.12},
            "evalplus": {"passed": False, "variant": "base-plus"},
        },
    }

    run = parse_humaneval_record(record)
    original = original_pass_reducer(record)
    evalplus = evalplus_pass_reducer(record)

    assert run.instance_key == "HumanEval/2"
    assert run.schema_fit_class == "row-record"
    assert one_resource_named(run.resources, "completion.py").payload == "    return not x\n"

    assert original.name == "humaneval.original_pass"
    assert original.output == {"passed": True}
    assert original.fields_read == ["original_passed", "driver_results.original.passed"]

    assert evalplus.name == "humaneval.evalplus_pass"
    assert evalplus.output == {"passed": False}
    assert evalplus.fields_read == ["evalplus_passed", "driver_results.evalplus.passed"]
    assert evalplus.drops[0].dropped_field_path == "evalplus.test_suite_delta"
    assert evalplus.drops[0].affected_analysis == "humaneval.evalplus_pass"


def one_resource_named(resources, name: str):
    matches = [resource for resource in resources if resource.name == name]
    assert len(matches) == 1
    return matches[0]
