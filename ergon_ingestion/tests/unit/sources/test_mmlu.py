import importlib
import json
from pathlib import Path

import pytest

from ergon_ingestion.models import ImportSource


def test_mmlu_importer_parses_jsonl_rows_with_accuracy_and_convention_reducers(
    tmp_path: Path,
) -> None:
    mmlu_module = _load_mmlu_module()
    source_path = tmp_path / "mmlu.jsonl"
    rows = [
        {
            "item_id": "abstract_algebra-0001",
            "model": "sample-model",
            "subject": "abstract_algebra",
            "question": "Which structure is a group?",
            "choices": ["A set", "A monoid with inverses", "A ring", "A field extension"],
            "gold": "B",
            "predicted": "B",
            "choice_logprobs": {"A": -3.2, "B": -0.1, "C": -2.7, "D": -1.9},
            "details": {"temperature": 0.0},
            "prompt_template": "cot-fewshot",
            "extraction_mode": "answer-letter",
        },
        {
            "item_id": "anatomy-0002",
            "model_name": "sample-model",
            "subject": "anatomy",
            "choices": ["heart", "lung", "kidney", "liver"],
            "answer": 2,
            "predicted_answer": "D",
            "full_prompt": "Question: ...",
            "generation": "The answer is D.",
            "extraction": {"mode": "regex-final-letter", "raw": "D"},
        },
    ]
    source_path.write_text("\n".join(json.dumps(row) for row in rows) + "\n")

    importer = mmlu_module.MmluImporter()
    report = importer.validate(
        ImportSource(dataset="mmlu", input_path=source_path, batch_id="mmlu-unit")
    )
    runs = list(
        importer.iter_runs(
            ImportSource(dataset="mmlu", input_path=source_path, batch_id="mmlu-unit")
        )
    )

    assert report.ok is True
    assert report.planned_runs == 2
    assert importer.info.schema_fit_class == "row-record"
    assert importer.info.default_reducers == [
        "mmlu.answer_accuracy",
        "mmlu.prompt_extraction_convention",
    ]
    assert [run.source_run_id for run in runs] == [
        "sample-model:abstract_algebra:abstract_algebra-0001",
        "sample-model:anatomy:anatomy-0002",
    ]

    first = runs[0]
    assert first.schema_fit_class == "row-record"
    assert first.instance_key == "abstract_algebra:abstract_algebra-0001"
    assert first.observed_fields["choices"] == rows[0]["choices"]
    assert first.observed_fields["choice_logprobs"] == rows[0]["choice_logprobs"]
    assert first.observed_fields["details"] == rows[0]["details"]
    assert set(first.missing_fields) == {"full_generation", "full_prompt"}
    assert first.resources[0].kind == "import"
    assert first.resources[0].payload == rows[0]

    reducers = {reducer.name: reducer for reducer in first.reducers}
    assert set(reducers) == {"mmlu.answer_accuracy", "mmlu.prompt_extraction_convention"}
    assert reducers["mmlu.answer_accuracy"].fields_read == [
        "predicted",
        "predicted_answer",
        "gold",
        "answer",
        "choice_logprobs",
        "logprobs",
        "details",
    ]
    assert reducers["mmlu.answer_accuracy"].output == {
        "correct": True,
        "predicted_answer": "B",
        "gold_answer": "B",
        "subject": "abstract_algebra",
        "has_choice_logprobs": True,
    }
    assert {drop.dropped_field_path for drop in reducers["mmlu.answer_accuracy"].drops} == {
        "full_generation",
        "full_prompt",
    }

    convention = reducers["mmlu.prompt_extraction_convention"]
    assert convention.fields_read == [
        "prompt_template",
        "template",
        "extraction_mode",
        "extraction",
        "full_prompt",
        "prompt",
        "generation",
        "full_generation",
    ]
    assert convention.output == {
        "prompt_template": "cot-fewshot",
        "extraction_mode": "answer-letter",
        "has_full_prompt": False,
        "has_full_generation": False,
    }

    second_reducers = {reducer.name: reducer for reducer in runs[1].reducers}
    assert second_reducers["mmlu.answer_accuracy"].output["gold_answer"] == "C"
    assert second_reducers["mmlu.answer_accuracy"].output["correct"] is False
    assert runs[1].missing_fields == []
    assert not second_reducers["mmlu.answer_accuracy"].drops


def test_parse_mmlu_row_accepts_prompt_and_extraction_variants() -> None:
    mmlu_module = _load_mmlu_module()
    run = mmlu_module.parse_mmlu_row(
        {
            "id": "row-3",
            "model_id": "another-model",
            "subject": "world_religions",
            "choices": ["A", "B", "C", "D"],
            "target": "A",
            "prediction": " a ",
            "template": "zero-shot",
            "prompt": "Pick an answer.",
            "full_generation": "",
            "logprobs": {"A": -0.2},
            "extraction_mode": "strip-uppercase",
        },
        fallback_id="fallback",
    )

    assert run.source_run_id == "another-model:world_religions:row-3"
    assert run.schema_fit_class == "row-record"
    assert run.missing_fields == ["full_generation"]

    reducers = {reducer.name: reducer for reducer in run.reducers}
    assert reducers["mmlu.answer_accuracy"].output["correct"] is True
    assert reducers["mmlu.answer_accuracy"].output["gold_answer"] == "A"
    assert reducers["mmlu.answer_accuracy"].output["predicted_answer"] == "A"
    assert reducers["mmlu.prompt_extraction_convention"].output == {
        "prompt_template": "zero-shot",
        "extraction_mode": "strip-uppercase",
        "has_full_prompt": True,
        "has_full_generation": False,
    }


def _load_mmlu_module():
    try:
        return importlib.import_module("ergon_ingestion.sources.mmlu")
    except ModuleNotFoundError as exc:
        pytest.fail(f"MMLU source parser is not implemented: {exc}")
