import json
from pathlib import Path

from ergon_ingestion.models import ImportSource
from ergon_ingestion.reducers.atbench import reduce_outcome, reduce_trajectory_summary
from ergon_ingestion.sources.atbench import AtBenchImporter


VALID_RESOURCE_KINDS = {"import", "artifact", "report", "output", "search_cache", "note"}


def test_atbench_importer_preserves_json_trace_events_resources_and_reducers(
    tmp_path: Path,
) -> None:
    source_path = write_atbench_json_fixture(tmp_path)
    importer = AtBenchImporter()

    runs = list(
        importer.iter_runs(
            ImportSource(dataset="atbench", input_path=source_path, batch_id="atbench-unit")
        )
    )

    assert [run.source_run_id for run in runs] == ["traj-json-001", "traj-json-002"]
    assert runs[0].instance_key == "task-json-001"
    assert runs[0].schema_fit_class == "full-trace"
    assert runs[0].observed_fields["trajectory_id"] == "traj-json-001"
    assert runs[0].observed_fields["task_id"] == "task-json-001"
    assert runs[0].observed_fields["score"] == 0.75
    assert runs[0].observed_fields["success"] is True
    assert runs[0].observed_fields["outcome"] == "passed"
    assert runs[0].observed_fields["task_metadata"] == {"domain": "calendar", "difficulty": "easy"}

    assert [event.event_type for event in runs[0].events] == [
        "step",
        "action",
        "tool_call",
    ]
    assert runs[0].events[0].payload == {
        "step_index": 0,
        "content": "Read the user's calendar request.",
        "status": "ok",
    }
    assert runs[0].events[1].payload == {
        "action_index": 0,
        "name": "inspect_calendar",
        "arguments": {"date": "2026-04-30"},
        "result": "free at 3pm",
        "status": "ok",
    }
    assert runs[0].events[2].payload == {
        "tool_call_index": 0,
        "id": "call-json-1",
        "name": "create_event",
        "arguments": {"time": "3pm"},
        "result": {"event_id": "evt-1"},
        "status": "ok",
    }

    assert [resource.kind for resource in runs[0].resources] == [
        "import",
        "artifact",
        "artifact",
        "artifact",
    ]
    assert all(resource.kind in VALID_RESOURCE_KINDS for resource in runs[0].resources)
    assert runs[0].resources[1].payload["steps"] == runs[0].observed_fields["steps"]
    assert runs[0].resources[2].payload["actions"] == runs[0].observed_fields["actions"]
    assert runs[0].resources[3].payload["tool_calls"] == runs[0].observed_fields["tool_calls"]

    reducers = {reducer.name: reducer for reducer in runs[0].reducers}
    assert set(reducers) == {"atbench.outcome", "atbench.trajectory_summary"}
    assert reducers["atbench.outcome"].fields_read == [
        "outcome",
        "success",
        "score",
        "evaluator",
        "evaluator_metadata",
    ]
    assert reducers["atbench.outcome"].output == {
        "outcome": "passed",
        "success": True,
        "score": 0.75,
        "evaluator_metadata_present": False,
    }
    assert reducers["atbench.trajectory_summary"].fields_read == [
        "steps",
        "actions",
        "tool_calls",
        "outcome",
        "success",
        "score",
    ]
    assert reducers["atbench.trajectory_summary"].output == {
        "step_summaries": ["Read the user's calendar request."],
        "action_summaries": ["inspect_calendar"],
        "tool_call_summaries": ["create_event"],
        "step_count": 1,
        "action_count": 1,
        "tool_call_count": 1,
        "has_full_trace": True,
        "outcome": "passed",
        "success": True,
        "score": 0.75,
    }

    summary_drops = {
        (drop.reason, drop.dropped_field_path)
        for reducer in runs[1].reducers
        for drop in reducer.drops
    }
    assert ("row_summary_missing_full_trace_detail", "steps/actions/tool_calls") in summary_drops
    assert ("source_replay_metadata_unavailable", "replay") in summary_drops
    assert ("source_evaluator_metadata_unavailable", "evaluator_metadata") in summary_drops


def test_atbench_importer_reads_csv_summary_and_declares_missing_trace_detail(
    tmp_path: Path,
) -> None:
    source_path = write_atbench_csv_fixture(tmp_path)
    importer = AtBenchImporter()

    runs = list(
        importer.iter_runs(
            ImportSource(dataset="atbench", input_path=source_path, batch_id="atbench-csv")
        )
    )

    assert [run.source_run_id for run in runs] == ["traj-csv-001"]
    assert runs[0].instance_key == "task-csv-001"
    assert runs[0].schema_fit_class == "full-trace"
    assert runs[0].observed_fields["trajectory_id"] == "traj-csv-001"
    assert runs[0].observed_fields["task_id"] == "task-csv-001"
    assert runs[0].observed_fields["score"] == 1.0
    assert runs[0].observed_fields["success"] is True
    assert runs[0].observed_fields["outcome"] == "solved"
    assert runs[0].events == []
    assert [resource.kind for resource in runs[0].resources] == ["import"]

    missing = {drop.dropped_field_path for reducer in runs[0].reducers for drop in reducer.drops}
    assert "steps/actions/tool_calls" in missing
    assert "replay" in missing
    assert "evaluator_metadata" in missing


def test_atbench_reducers_read_outcome_trace_fields_and_declare_drops() -> None:
    full_trace_record, summary_record = atbench_json_records()

    outcome = reduce_outcome(summary_record)
    summary = reduce_trajectory_summary(summary_record)
    full_summary = reduce_trajectory_summary(full_trace_record)

    assert outcome.name == "atbench.outcome"
    assert outcome.kind == "original"
    assert outcome.fields_read == [
        "outcome",
        "success",
        "score",
        "evaluator",
        "evaluator_metadata",
    ]
    assert outcome.output == {
        "outcome": "failed",
        "success": False,
        "score": 0.0,
        "evaluator_metadata_present": False,
    }

    assert summary.name == "atbench.trajectory_summary"
    assert summary.kind == "recovered"
    assert summary.fields_read == [
        "steps",
        "actions",
        "tool_calls",
        "outcome",
        "success",
        "score",
    ]
    assert summary.output["has_full_trace"] is False
    assert summary.output["step_summaries"] == []
    assert summary.output["action_summaries"] == []
    assert summary.output["tool_call_summaries"] == []

    assert full_summary.output["has_full_trace"] is True
    assert full_summary.output["step_summaries"] == ["Read the user's calendar request."]
    assert full_summary.output["action_summaries"] == ["inspect_calendar"]
    assert full_summary.output["tool_call_summaries"] == ["create_event"]

    declared_drops = {
        (drop.reason, drop.dropped_field_path) for drop in outcome.drops + summary.drops
    }
    assert ("row_summary_missing_full_trace_detail", "steps/actions/tool_calls") in declared_drops
    assert ("source_replay_metadata_unavailable", "replay") in declared_drops
    assert ("source_evaluator_metadata_unavailable", "evaluator_metadata") in declared_drops


def write_atbench_json_fixture(tmp_path: Path) -> Path:
    source_path = tmp_path / "atbench.json"
    source_path.write_text(json.dumps(atbench_json_records()))
    return source_path


def write_atbench_csv_fixture(tmp_path: Path) -> Path:
    source_path = tmp_path / "atbench.csv"
    source_path.write_text(
        "\n".join(
            [
                "trajectory_id,task_id,score,success,outcome,task_metadata",
                'traj-csv-001,task-csv-001,1.0,true,solved,"{""domain"": ""browser""}"',
            ]
        )
    )
    return source_path


def atbench_json_records() -> list[dict]:
    return [
        {
            "trajectory_id": "traj-json-001",
            "task_id": "task-json-001",
            "score": 0.75,
            "success": True,
            "outcome": "passed",
            "task_metadata": {"domain": "calendar", "difficulty": "easy"},
            "steps": [
                {
                    "content": "Read the user's calendar request.",
                    "status": "ok",
                }
            ],
            "actions": [
                {
                    "name": "inspect_calendar",
                    "arguments": {"date": "2026-04-30"},
                    "result": "free at 3pm",
                    "status": "ok",
                }
            ],
            "tool_calls": [
                {
                    "id": "call-json-1",
                    "name": "create_event",
                    "arguments": {"time": "3pm"},
                    "result": {"event_id": "evt-1"},
                    "status": "ok",
                }
            ],
        },
        {
            "trajectory_id": "traj-json-002",
            "task_id": "task-json-002",
            "score": 0.0,
            "success": False,
            "outcome": "failed",
            "task_metadata": {"domain": "spreadsheet"},
        },
    ]
