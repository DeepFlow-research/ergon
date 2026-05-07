import json
from pathlib import Path

from ergon_ingestion.models import ImportSource
from ergon_ingestion.reducers.gpqa import driver_variant_reducer, extracted_accuracy_reducer
from ergon_ingestion.sources.gpqa import GpqaImporter


def test_gpqa_importer_parses_row_records_with_generation_resources_and_reducers(
    tmp_path: Path,
) -> None:
    source_path = write_gpqa_fixture(tmp_path)
    importer = GpqaImporter()

    runs = list(
        importer.iter_runs(
            ImportSource(dataset="gpqa", input_path=source_path, batch_id="gpqa-unit")
        )
    )

    assert [run.source_run_id for run in runs] == ["gpqa-001", "gpqa-002"]
    assert [run.schema_fit_class for run in runs] == ["row-record", "row-record"]
    assert runs[0].instance_key == "gpqa-001"
    assert runs[0].observed_fields["question"] == "Which particle mediates electromagnetism?"
    assert runs[0].observed_fields["gold_answer"] == "photon"
    assert runs[0].observed_fields["generation"] == "The answer is photon."
    assert runs[0].observed_fields["extracted_answer"] == "photon"
    assert runs[0].missing_fields == ["extraction.registry_match"]

    resources = {resource.name: resource for resource in runs[0].resources}
    assert resources["source-record.json"].kind == "import"
    assert resources["generation.txt"].kind == "output"
    assert resources["generation.txt"].payload == "The answer is photon."

    reducers = {reducer.name: reducer for reducer in runs[0].reducers}
    assert set(reducers) == {"gpqa.extracted_accuracy", "gpqa.driver_variant"}
    assert reducers["gpqa.extracted_accuracy"].fields_read == [
        "gold_answer",
        "extracted_answer",
        "correct",
        "passed",
    ]
    assert reducers["gpqa.extracted_accuracy"].output == {
        "gold_answer": "photon",
        "extracted_answer": "photon",
        "correct": True,
        "passed": True,
    }
    assert reducers["gpqa.driver_variant"].fields_read == [
        "driver_mode",
        "extractor_mode",
        "generation",
        "extracted_answer",
    ]
    assert reducers["gpqa.driver_variant"].output == {
        "driver_mode": "near_null",
        "extractor_mode": "regex",
        "generation": "The answer is photon.",
        "extracted_answer": "photon",
    }

    drop_reasons = {drop.reason for reducer in runs[0].reducers for drop in reducer.drops}
    assert "extraction_registry_mismatch_caveat" in drop_reasons


def test_gpqa_reducers_preserve_extractor_fields_and_declare_mismatch_caveat() -> None:
    record = gpqa_records()[1]

    accuracy = extracted_accuracy_reducer(record)
    variant = driver_variant_reducer(record)

    assert accuracy.name == "gpqa.extracted_accuracy"
    assert accuracy.output == {
        "gold_answer": "mitochondrion",
        "extracted_answer": "chloroplast",
        "correct": False,
        "passed": False,
    }
    assert accuracy.fields_read == ["gold_answer", "extracted_answer", "correct", "passed"]

    assert variant.name == "gpqa.driver_variant"
    assert variant.output == {
        "driver_mode": "registry",
        "extractor_mode": "llm",
        "generation": "I choose chloroplast.",
        "extracted_answer": "chloroplast",
    }
    assert variant.fields_read == [
        "driver_mode",
        "extractor_mode",
        "generation",
        "extracted_answer",
    ]

    declared_missing = {
        drop.dropped_field_path for reducer in [accuracy, variant] for drop in reducer.drops
    }
    assert "extraction.registry_match" in declared_missing


def write_gpqa_fixture(tmp_path: Path) -> Path:
    source_path = tmp_path / "gpqa.jsonl"
    source_path.write_text("\n".join(json.dumps(record) for record in gpqa_records()))
    return source_path


def gpqa_records() -> list[dict[str, object]]:
    return [
        {
            "item_id": "gpqa-001",
            "question": "Which particle mediates electromagnetism?",
            "gold_answer": "photon",
            "generation": "The answer is photon.",
            "extracted_answer": "photon",
            "driver_mode": "near_null",
            "extractor_mode": "regex",
            "passed": True,
            "correct": True,
        },
        {
            "item_id": "gpqa-002",
            "question": "Which organelle is the powerhouse of the cell?",
            "gold_answer": "mitochondrion",
            "generation": "I choose chloroplast.",
            "extracted_answer": "chloroplast",
            "driver_mode": "registry",
            "extractor_mode": "llm",
            "passed": False,
            "correct": False,
        },
    ]
