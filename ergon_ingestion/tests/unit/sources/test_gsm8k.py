import json
from pathlib import Path

import pytest

from ergon_ingestion.models import ImportSource


def test_gsm8k_importer_parses_jsonl_rows_with_accuracy_and_convention_reducers(
    tmp_path: Path,
) -> None:
    source_module = _load_gsm8k_source_module()
    source_path = write_gsm8k_fixture(tmp_path)
    importer = source_module.Gsm8kImporter()

    report = importer.validate(
        ImportSource(dataset="gsm8k", input_path=source_path, batch_id="gsm8k-unit")
    )
    runs = list(
        importer.iter_runs(
            ImportSource(dataset="gsm8k", input_path=source_path, batch_id="gsm8k-unit")
        )
    )

    assert report.ok is True
    assert report.planned_runs == 2
    assert importer.info.schema_fit_class == "row-record"
    assert importer.info.default_reducers == [
        "gsm8k.extracted_accuracy",
        "gsm8k.answer_format_convention",
    ]
    assert [run.source_run_id for run in runs] == ["gsm8k-001", "gsm8k-002"]

    first = runs[0]
    assert first.schema_fit_class == "row-record"
    assert first.instance_key == "gsm8k-001"
    assert first.observed_fields["question"] == "Jan has 14 apples and buys 28 more. How many?"
    assert first.observed_fields["gold_answer"] == "#### 42"
    assert first.observed_fields["completion"] == "14 + 28 = 42. #### 42"
    assert first.observed_fields["extracted_answer"] == "42"
    assert first.observed_fields["convention"] == "hash_delimited"
    assert first.observed_fields["mode"] == "fixed_completion"

    resources = {resource.name: resource for resource in first.resources}
    assert {resource.kind for resource in resources.values()} <= {
        "import",
        "artifact",
        "report",
        "output",
        "search_cache",
        "note",
    }
    assert resources["source-record.json"].kind == "import"
    assert resources["completion.txt"].kind == "output"

    reducers = {reducer.name: reducer for reducer in first.reducers}
    assert set(reducers) == {
        "gsm8k.extracted_accuracy",
        "gsm8k.answer_format_convention",
    }
    assert reducers["gsm8k.extracted_accuracy"].fields_read == [
        "gold_answer",
        "answer",
        "completion",
        "extracted_answer",
        "correct",
        "passed",
    ]
    assert reducers["gsm8k.extracted_accuracy"].output == {
        "gold_answer": "42",
        "extracted_answer": "42",
        "correct": True,
        "passed": True,
        "has_completion": True,
    }
    assert reducers["gsm8k.answer_format_convention"].fields_read == [
        "convention",
        "mode",
        "extractor_mode",
        "completion",
        "gold_answer",
        "answer",
        "extracted_answer",
    ]
    assert reducers["gsm8k.answer_format_convention"].output == {
        "convention": "hash_delimited",
        "mode": "fixed_completion",
        "extractor_mode": "regex_hash_or_final_number",
        "has_hash_delimiter": True,
        "has_boxed_answer": False,
        "weak_model_formatting": False,
    }

    drop_reasons = {drop.reason for reducer in first.reducers for drop in reducer.drops}
    assert "answer_format_convention_dependent" in drop_reasons

    second_reducers = {reducer.name: reducer for reducer in runs[1].reducers}
    assert second_reducers["gsm8k.extracted_accuracy"].output == {
        "gold_answer": "18",
        "extracted_answer": "19",
        "correct": False,
        "passed": False,
        "has_completion": True,
    }
    assert second_reducers["gsm8k.answer_format_convention"].output["convention"] == "plain"
    assert second_reducers["gsm8k.answer_format_convention"].output["weak_model_formatting"] is True


def test_gsm8k_reducers_normalize_gold_and_extracted_answers_with_format_caveats() -> None:
    reducers_module = _load_gsm8k_reducers_module()
    record = {
        "question_id": "gsm8k-003",
        "question": "What is 20 divided by 5?",
        "answer": "We compute 20 / 5. #### 4",
        "completion": "The answer is \\boxed{4}.",
        "extracted_answer": " 4 ",
        "convention": "boxed",
        "mode": "fixed_completion",
        "extractor_mode": "boxed_regex",
    }

    accuracy = reducers_module.extracted_accuracy_reducer(record)
    convention = reducers_module.answer_format_convention_reducer(record)

    assert accuracy.name == "gsm8k.extracted_accuracy"
    assert accuracy.output["gold_answer"] == "4"
    assert accuracy.output["extracted_answer"] == "4"
    assert accuracy.output["correct"] is True
    assert accuracy.fields_read

    assert convention.name == "gsm8k.answer_format_convention"
    assert convention.output == {
        "convention": "boxed",
        "mode": "fixed_completion",
        "extractor_mode": "boxed_regex",
        "has_hash_delimiter": True,
        "has_boxed_answer": True,
        "weak_model_formatting": False,
    }
    assert convention.fields_read

    declared_drops = {
        drop.dropped_field_path for reducer in [accuracy, convention] for drop in reducer.drops
    }
    assert "answer.format_convention" in declared_drops
    assert "answer.normalization_provenance" in declared_drops


def write_gsm8k_fixture(tmp_path: Path) -> Path:
    source_path = tmp_path / "gsm8k.jsonl"
    source_path.write_text("\n".join(json.dumps(record) for record in gsm8k_records()) + "\n")
    return source_path


def gsm8k_records() -> list[dict[str, object]]:
    return [
        {
            "item_id": "gsm8k-001",
            "question": "Jan has 14 apples and buys 28 more. How many?",
            "gold_answer": "#### 42",
            "completion": "14 + 28 = 42. #### 42",
            "extracted_answer": "42",
            "convention": "hash_delimited",
            "mode": "fixed_completion",
            "extractor_mode": "regex_hash_or_final_number",
            "passed": True,
        },
        {
            "question_id": "gsm8k-002",
            "question": "A pack has 9 pencils. How many in 2 packs?",
            "answer": "9 * 2 = 18",
            "completion": "I think it is probably 19",
            "extracted_answer": "19",
            "convention": "plain",
            "mode": "weak_model_fixed_completion",
            "extractor_mode": "final_number",
        },
    ]


def _load_gsm8k_source_module():
    try:
        from ergon_ingestion.sources import gsm8k
    except ModuleNotFoundError as exc:
        pytest.fail(f"GSM8K source parser is not implemented: {exc}")
    return gsm8k


def _load_gsm8k_reducers_module():
    try:
        from ergon_ingestion.reducers import gsm8k
    except ModuleNotFoundError as exc:
        pytest.fail(f"GSM8K reducers are not implemented: {exc}")
    return gsm8k
