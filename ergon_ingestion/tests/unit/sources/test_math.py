import json
from importlib import import_module
from pathlib import Path

from ergon_ingestion.models import ImportSource


def test_math_importer_parses_jsonl_rows_and_declares_local_reducers(tmp_path: Path) -> None:
    fixture = tmp_path / "math.jsonl"
    rows = [
        {
            "problem_id": "algebra-001",
            "problem": "Compute 6 * 7.",
            "solution": "The answer is \\boxed{42}.",
            "completion": "We multiply and get \\boxed{42}.",
            "extracted_answer": "42",
            "boxed": True,
            "normalization_mode": "boxed_integer",
        },
        {
            "problem_id": "algebra-002",
            "problem": "Solve x + 2 = 5.",
            "gold_answer": "3",
            "model_answer": "x = 3",
            "extracted_answer": "3",
            "convention": "strip_equation_prefix",
        },
    ]
    fixture.write_text("\n".join(json.dumps(row) for row in rows))
    importer = _math_importer()
    source = ImportSource(dataset="math", input_path=fixture, batch_id="math-unit")

    report = importer.validate(source)
    runs = list(importer.iter_runs(source))

    assert report.ok
    assert report.planned_runs == 2
    assert importer.info.schema_fit_class == "row-record"
    assert importer.info.default_reducers == [
        "math.extracted_accuracy",
        "math.normalization_convention",
    ]
    assert [run.source_run_id for run in runs] == ["algebra-001", "algebra-002"]
    assert all(run.schema_fit_class == "row-record" for run in runs)
    assert runs[0].observed_fields["completion"] == "We multiply and get \\boxed{42}."
    assert runs[1].observed_fields["model_answer"] == "x = 3"
    assert {resource.kind for resource in runs[0].resources} == {"import", "output"}
    assert {resource.kind for resource in runs[1].resources} == {"import", "output"}


def test_math_reducers_preserve_extraction_fields_and_missing_judge_caveat() -> None:
    parse_math_record = _math_module().parse_math_record
    run = parse_math_record(
        {
            "problem_id": "number-theory-001",
            "problem": "What is 10 mod 4?",
            "solution": "\\boxed{2}",
            "completion": "The remainder is 2.",
            "extracted_answer": "2",
            "boxed": True,
            "normalization_mode": "boxed_integer",
        }
    )

    reducers = {reducer.name: reducer for reducer in run.reducers}
    accuracy = reducers["math.extracted_accuracy"]
    convention = reducers["math.normalization_convention"]

    assert accuracy.output == {
        "gold_answer": "\\boxed{2}",
        "completion": "The remainder is 2.",
        "extracted_answer": "2",
        "correct": None,
        "llm_judge": None,
    }
    assert "solution" in accuracy.fields_read
    assert "completion" in accuracy.fields_read
    assert "extracted_answer" in accuracy.fields_read
    assert convention.output == {
        "boxed": True,
        "normalization_mode": "boxed_integer",
        "convention": None,
        "extracted_answer": "2",
    }
    assert "llm_judge.regrade" in run.missing_fields
    assert {drop.dropped_field_path for reducer in run.reducers for drop in reducer.drops} == {
        "llm_judge.regrade"
    }
    assert all(
        drop.declaration_kind == "source_missing"
        for reducer in run.reducers
        for drop in reducer.drops
    )


def _math_importer():
    return _math_module().MathImporter()


def _math_module():
    try:
        return import_module("ergon_ingestion.sources.math")
    except ModuleNotFoundError as exc:
        raise AssertionError("ergon_ingestion.sources.math must define MathImporter") from exc
