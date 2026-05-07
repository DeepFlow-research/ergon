import importlib
import json
from pathlib import Path

import pytest

from ergon_ingestion.models import ImportSource


def test_browsecomp_importer_parses_answer_rows_resources_and_reducers(tmp_path: Path) -> None:
    browsecomp_module = _load_browsecomp_module()
    source_path = write_browsecomp_fixture(tmp_path)

    importer = browsecomp_module.BrowseCompImporter()
    runs = list(
        importer.iter_runs(
            ImportSource(dataset="browsecomp", input_path=source_path, batch_id="browsecomp-unit")
        )
    )

    assert [run.source_run_id for run in runs] == ["bc-001", "bc-002"]
    assert [run.schema_fit_class for run in runs] == ["row-record", "row-record"]
    assert runs[0].instance_key == "bc-001"
    assert runs[0].observed_fields["gold_answer"] == "Ada Lovelace"
    assert runs[0].observed_fields["predicted_answer"] == "  ada   lovelace "
    assert "browsing_trace" in runs[0].missing_fields

    answers = one_by_namespace(runs[0].annotations, "browsecomp.answers")
    assert answers.payload == {
        "question_id": "bc-001",
        "gold_answer": "Ada Lovelace",
        "predicted_answer": "  ada   lovelace ",
        "status": "answered",
    }

    judge = one_by_namespace(runs[0].annotations, "browsecomp.judge")
    assert judge.payload == {
        "judge_result": "correct",
        "judge_explanation": "The predicted answer names the same person.",
    }

    metadata = one_by_namespace(runs[0].annotations, "browsecomp.metadata")
    assert metadata.payload == {
        "canary": "unit-canary",
        "decryption_note": "fixture preserves note without decrypting",
    }

    assert runs[0].resources[0].name == "source-row.json"
    assert runs[0].resources[0].kind == "import"
    assert runs[0].resources[0].payload["question_id"] == "bc-001"
    assert runs[0].resources[1].name == "judge-output.json"
    assert runs[0].resources[1].kind == "report"
    assert runs[0].resources[1].payload == judge.payload

    reducers = {reducer.name: reducer for reducer in runs[0].reducers}
    assert set(reducers) == {"browsecomp.exact_match", "browsecomp.llm_judge"}
    assert reducers["browsecomp.exact_match"].fields_read == ["gold_answer", "predicted_answer"]
    assert reducers["browsecomp.exact_match"].output == {
        "exact_match": True,
        "normalized_gold_answer": "ada lovelace",
        "normalized_predicted_answer": "ada lovelace",
    }
    assert reducers["browsecomp.llm_judge"].fields_read == [
        "judge_result",
        "judge_explanation",
    ]
    assert reducers["browsecomp.llm_judge"].output == {
        "judge_result": "correct",
        "judge_explanation": "The predicted answer names the same person.",
    }

    drop_reasons = {
        drop.reason
        for reducer in runs[0].reducers
        for drop in reducer.drops
    }
    assert "source_row_does_not_include_browsing_trace" in drop_reasons
    assert "source_llm_judge_is_stochastic_and_not_replayable_without_original_judge_context" in (
        drop_reasons
    )


def test_browsecomp_reducers_preserve_judge_fields_and_declare_caveats() -> None:
    reducers_module = _load_browsecomp_reducers_module()
    record = browsecomp_records()[1]

    exact_match = reducers_module.exact_match_reducer(record)
    llm_judge = reducers_module.llm_judge_reducer(record)

    assert exact_match.name == "browsecomp.exact_match"
    assert exact_match.kind == "original"
    assert exact_match.fields_read == ["gold_answer", "predicted_answer"]
    assert exact_match.output == {
        "exact_match": False,
        "normalized_gold_answer": "alan turing",
        "normalized_predicted_answer": "ada lovelace",
    }

    assert llm_judge.name == "browsecomp.llm_judge"
    assert llm_judge.kind == "original"
    assert llm_judge.fields_read == ["judge_result", "judge_explanation"]
    assert llm_judge.output == {
        "judge_result": "incorrect",
        "judge_explanation": "The prediction names a different person.",
    }

    declared_missing = {
        drop.dropped_field_path
        for reducer in [exact_match, llm_judge]
        for drop in reducer.drops
    }
    assert "browsing_trace" in declared_missing
    assert "judge.replay_context" in declared_missing


def write_browsecomp_fixture(tmp_path: Path) -> Path:
    source_path = tmp_path / "browsecomp.jsonl"
    source_path.write_text("\n".join(json.dumps(record) for record in browsecomp_records()))
    return source_path


def browsecomp_records() -> list[dict]:
    return [
        {
            "question_id": "bc-001",
            "question": "Who wrote the first published computer program?",
            "gold_answer": "Ada Lovelace",
            "predicted_answer": "  ada   lovelace ",
            "judge_result": "correct",
            "judge_explanation": "The predicted answer names the same person.",
            "status": "answered",
            "canary": "unit-canary",
            "decryption_note": "fixture preserves note without decrypting",
        },
        {
            "question_id": "bc-002",
            "question": "Who proposed the Turing test?",
            "gold_answer": "Alan Turing",
            "predicted_answer": "Ada Lovelace",
            "judge_result": "incorrect",
            "judge_explanation": "The prediction names a different person.",
            "status": "judged",
            "canary_note": "second fixture canary",
        },
    ]


def _load_browsecomp_module():
    try:
        return importlib.import_module("ergon_ingestion.sources.browsecomp")
    except ModuleNotFoundError as exc:
        pytest.fail(f"BrowseComp source parser is not implemented: {exc}")


def _load_browsecomp_reducers_module():
    try:
        return importlib.import_module("ergon_ingestion.reducers.browsecomp")
    except ModuleNotFoundError as exc:
        pytest.fail(f"BrowseComp reducers are not implemented: {exc}")


def one_by_namespace(annotations, namespace: str):
    matches = [annotation for annotation in annotations if annotation.namespace == namespace]
    assert len(matches) == 1
    return matches[0]
