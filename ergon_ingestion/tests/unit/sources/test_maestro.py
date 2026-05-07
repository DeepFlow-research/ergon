import json
from pathlib import Path

from ergon_ingestion.models import ImportSource, ParsedRun
from ergon_ingestion.sources.maestro import MaestroImporter, parse_maestro_runs


def test_parse_maestro_rows_groups_spans_by_run_id() -> None:
    runs = parse_maestro_runs(_maestro_rows())

    assert [run.source_run_id for run in runs] == ["run-alpha", "run-beta"]
    assert all(run.schema_fit_class == "span-trace" for run in runs)
    assert [_span_count(run) for run in runs] == [3, 2]
    assert runs[0].resources[0].kind == "artifact"
    assert runs[0].events[0].event_type == "maestro.span"


def test_parse_maestro_rows_preserves_outcomes_and_reducer_declarations() -> None:
    runs = parse_maestro_runs(_maestro_rows())
    alpha = runs[0]

    assert _annotation_payload(alpha, "maestro.outcome") == {
        "outcome": "success",
        "judgement": "accepted",
    }

    reducers = {reducer.name: reducer for reducer in alpha.reducers}
    assert {"maestro.outcome", "maestro.coordination_overhead"} <= set(reducers)
    assert reducers["maestro.outcome"].output == {
        "outcome": "success",
        "judgement": "accepted",
    }
    assert reducers["maestro.coordination_overhead"].output["span_count"] == 3
    assert reducers["maestro.coordination_overhead"].output["token_count"] == 72
    assert reducers["maestro.coordination_overhead"].output["status_counts"] == {
        "OK": 2,
        "ERROR": 1,
    }

    fields_read = set(reducers["maestro.coordination_overhead"].fields_read)
    assert {"span_id", "duration_ms", "token_count", "attributes.run.outcome"} <= fields_read

    drop_text = " ".join(drop.reason for reducer in reducers.values() for drop in reducer.drops)
    assert "coordination causality is not observed" in drop_text
    assert "direct failure mechanism is not observed" in drop_text


def test_maestro_importer_reads_jsonl_fixture_grouped_by_run(tmp_path: Path) -> None:
    fixture_path = tmp_path / "maestro_spans.jsonl"
    fixture_path.write_text("\n".join(json.dumps(row) for row in _maestro_rows()))
    importer = MaestroImporter()

    report = importer.validate(
        ImportSource(dataset="maestro", input_path=fixture_path, batch_id="test-batch")
    )
    runs = list(
        importer.iter_runs(
            ImportSource(dataset="maestro", input_path=fixture_path, batch_id="test-batch")
        )
    )

    assert report.ok is True
    assert report.planned_runs == 2
    assert [run.source_run_id for run in runs] == ["run-alpha", "run-beta"]
    assert _annotation_payload(runs[1], "maestro.outcome") == {
        "outcome": "failure",
        "judgement": "rejected",
    }


def _maestro_rows() -> list[dict]:
    return [
        {
            "run_id": "run-alpha",
            "trace_id": "trace-alpha",
            "span_id": "alpha-root",
            "parent_span_id": None,
            "agent_name": "planner",
            "start_time": "2026-04-01T00:00:00Z",
            "duration_ms": 1000,
            "status": "OK",
            "token_count": 30,
            "attributes": {
                "run.outcome": "success",
                "run.judgement": "accepted",
                "communication.messages": 2,
            },
        },
        {
            "run_id": "run-alpha",
            "trace_id": "trace-alpha",
            "span_id": "alpha-worker",
            "parent_span_id": "alpha-root",
            "agent_name": "worker",
            "duration_ms": 2500,
            "status": "OK",
            "input_tokens": 10,
            "output_tokens": 20,
            "attributes": {"coordination.round": 1},
        },
        {
            "run_id": "run-alpha",
            "trace_id": "trace-alpha",
            "span_id": "alpha-reviewer",
            "parent_span_id": "alpha-root",
            "agent_name": "reviewer",
            "duration_ms": 500,
            "status": "ERROR",
            "error": "review timeout",
            "token_count": 12,
            "attributes": {"coordination.round": 1},
        },
        {
            "run_id": "run-beta",
            "trace_id": "trace-beta",
            "span_id": "beta-root",
            "parent_span_id": None,
            "agent_name": "planner",
            "duration_ms": 700,
            "status": "OK",
            "token_count": 18,
            "attributes": {
                "run": {"outcome": "failure", "judgement": "rejected"},
                "communication": {"messages": 1},
            },
        },
        {
            "run_id": "run-beta",
            "trace_id": "trace-beta",
            "span_id": "beta-worker",
            "parent_span_id": "beta-root",
            "agent_name": "worker",
            "duration_ms": 1500,
            "status": "OK",
            "output_tokens": 22,
            "attributes": {"coordination.round": 1},
        },
    ]


def _span_count(run: ParsedRun) -> int:
    return int(run.observed_fields["span_count"])


def _annotation_payload(run: ParsedRun, namespace: str) -> dict:
    annotations = {annotation.namespace: annotation.payload for annotation in run.annotations}
    return annotations[namespace]
