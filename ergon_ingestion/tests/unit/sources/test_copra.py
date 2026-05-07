from pathlib import Path

from ergon_ingestion.models import ImportSource, ParsedRun
from ergon_ingestion.sources.copra import (
    CopraLogImporter,
    parsed_run_from_copra_record,
    parsed_runs_from_copra_text,
)


def test_parsed_run_from_copra_record_preserves_result_cost_and_proof() -> None:
    run = parsed_run_from_copra_record(
        {
            "Theorem": "Nat.add_0_r",
            "SearchResult": "SUCCESS",
            "outcome": "proved",
            "StepsUsed": 7,
            "ElapsedTime": 1.25,
            "Proof": "intros n; induction n; auto.",
        },
        source_run_id="copra-1",
    )

    assert run.schema_fit_class == "artifact-only"
    assert run.source_run_id == "copra-1"
    assert run.instance_key == "Nat.add_0_r"
    assert run.observed_fields["SearchResult"] == "SUCCESS"
    assert run.observed_fields["StepsUsed"] == 7
    assert run.observed_fields["elapsed_seconds"] == 1.25
    assert run.resources[0].name == "proof-or-log.txt"
    assert run.resources[0].payload == "intros n; induction n; auto."

    reducers = {reducer.name: reducer for reducer in run.reducers}
    assert set(reducers) == {"copra.proved_failed", "copra.realised_search_cost"}
    assert reducers["copra.proved_failed"].output == {
        "proved": True,
        "outcome": "proved",
        "search_result": "SUCCESS",
    }
    assert reducers["copra.realised_search_cost"].output == {
        "steps_used": 7,
        "elapsed_seconds": 1.25,
        "proved": True,
    }
    assert "Proof" in reducers["copra.proved_failed"].fields_read
    assert "StepsUsed" in reducers["copra.realised_search_cost"].fields_read


def test_copra_text_log_blocks_emit_one_run_per_theorem_attempt() -> None:
    log_text = """
Theorem: Nat.add_0_r
SearchResult: SUCCESS
StepsUsed: 7
ElapsedTime: 1.25
Proof:
  intros n; induction n; auto.
---
Theorem: Nat.mul_0_r
SearchResult: FAILURE
StepsUsed: 11
ElapsedTime: 3.5
Log:
  search exhausted without proof
""".strip()

    runs = parsed_runs_from_copra_text(log_text, source_name="synthetic-copra.log")

    assert [run.instance_key for run in runs] == ["Nat.add_0_r", "Nat.mul_0_r"]
    assert all(isinstance(run, ParsedRun) for run in runs)
    assert all(run.schema_fit_class == "artifact-only" for run in runs)
    assert all(run.resources for run in runs)

    failure = runs[1]
    reducers = {reducer.name: reducer for reducer in failure.reducers}
    assert reducers["copra.proved_failed"].output["proved"] is False
    assert reducers["copra.realised_search_cost"].output["steps_used"] == 11
    assert failure.resources[0].payload == "search exhausted without proof"

    drops = [drop for reducer in failure.reducers for drop in reducer.drops]
    assert {
        (drop.dropped_field_path, drop.reason, drop.loss_class)
        for drop in drops
    } >= {
        ("failed_proof_states", "unavailable_in_source", "unavailable_source_field"),
        ("failed_tactic_branches", "unavailable_in_source", "unavailable_source_field"),
    }


def test_copra_importer_reads_file_and_reports_planned_runs(tmp_path: Path) -> None:
    source_path = tmp_path / "copra.log"
    source_path.write_text(
        """
Theorem: first
SearchResult: SUCCESS
StepsUsed: 1
ElapsedTime: 0.1
Proof: exact I.
---
Theorem: second
SearchResult: FAILURE
StepsUsed: 2
ElapsedTime: 0.2
Log: no proof found
""".strip()
    )
    importer = CopraLogImporter()
    source = ImportSource(dataset="copra", input_path=source_path, batch_id="batch")

    report = importer.validate(source)
    runs = list(importer.iter_runs(source))

    assert report.ok is True
    assert report.planned_runs == 2
    assert [run.source_run_id for run in runs] == ["copra.log:1", "copra.log:2"]
