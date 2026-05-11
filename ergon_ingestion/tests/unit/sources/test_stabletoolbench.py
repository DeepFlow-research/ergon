import json
from pathlib import Path

from ergon_ingestion.models import ImportSource
from ergon_ingestion.reducers.stabletoolbench import reduce_tool_path, reduce_win
from ergon_ingestion.sources.stabletoolbench import StableToolBenchImporter


VALID_RESOURCE_KINDS = {"import", "artifact", "report", "output", "search_cache", "note"}


def test_stabletoolbench_importer_preserves_tool_trace_and_declares_caveats(
    tmp_path: Path,
) -> None:
    source_path = write_stabletoolbench_fixture(tmp_path)
    importer = StableToolBenchImporter()

    runs = list(
        importer.iter_runs(
            ImportSource(
                dataset="stabletoolbench",
                input_path=source_path,
                batch_id="stabletoolbench-unit",
            )
        )
    )

    assert [run.source_run_id for run in runs] == ["traj-001", "traj-002"]
    assert runs[0].instance_key == "task-alpha"
    assert runs[0].schema_fit_class == "full-trace"
    assert runs[0].observed_fields["trajectory_id"] == "traj-001"
    assert runs[0].observed_fields["task_id"] == "task-alpha"
    assert runs[0].observed_fields["is_solved"] is True
    assert runs[0].observed_fields["win"] is True
    assert runs[0].observed_fields["evaluator_statuses"] == ["passed"]

    assert [event.event_type for event in runs[0].events] == ["tool_step", "tool_step"]
    assert runs[0].events[0].payload == {
        "step_index": 0,
        "tool_name": "search",
        "arguments": {"query": "weather in London"},
        "response": {"results": ["rain forecast"]},
        "status": "ok",
    }
    assert runs[0].events[1].payload["tool_name"] == "lookup_weather"

    assert [resource.kind for resource in runs[0].resources] == ["import", "artifact"]
    assert all(resource.kind in VALID_RESOURCE_KINDS for resource in runs[0].resources)
    assert runs[0].resources[0].payload["answer_steps"][0]["tool"] == "search"
    assert runs[0].resources[1].payload["answer_steps"] == runs[0].observed_fields["answer_steps"]

    reducers = {reducer.name: reducer for reducer in runs[0].reducers}
    assert set(reducers) == {"stabletoolbench.win", "stabletoolbench.tool_path"}
    assert reducers["stabletoolbench.win"].fields_read == [
        "is_solved",
        "win",
        "pass",
        "evaluator.status",
        "evaluator_statuses",
    ]
    assert reducers["stabletoolbench.win"].output == {
        "win": True,
        "is_solved": True,
        "pass": None,
        "evaluator_statuses": ["passed"],
    }
    assert reducers["stabletoolbench.tool_path"].fields_read == [
        "answer_steps.tool",
        "answer_steps.tool_name",
        "answer_steps.name",
        "answer_steps.arguments",
        "answer_steps.args",
        "answer_steps.response",
        "answer_steps.status",
        "is_solved",
        "win",
    ]
    assert reducers["stabletoolbench.tool_path"].output == {
        "is_successful": True,
        "tool_path": ["search", "lookup_weather"],
        "tool_count": 2,
        "unique_tool_names": ["lookup_weather", "search"],
        "tool_argument_keys": [["query"], ["city"]],
        "response_count": 2,
        "malformed_answer_step_count": 0,
    }

    drop_reasons = {drop.reason for reducer in runs[0].reducers for drop in reducer.drops}
    assert "trusts_source_evaluator_statuses_without_regrading" in drop_reasons

    malformed_drop_reasons = {drop.reason for reducer in runs[1].reducers for drop in reducer.drops}
    assert "skipped_malformed_answer_step_members" in malformed_drop_reasons


def test_stabletoolbench_reducers_read_win_tool_path_and_declare_drops() -> None:
    record = stabletoolbench_records()[1]

    win = reduce_win(record)
    tool_path = reduce_tool_path(record)

    assert win.name == "stabletoolbench.win"
    assert win.kind == "original"
    assert win.fields_read == [
        "is_solved",
        "win",
        "pass",
        "evaluator.status",
        "evaluator_statuses",
    ]
    assert win.output == {
        "win": False,
        "is_solved": None,
        "pass": False,
        "evaluator_statuses": ["failed"],
    }

    assert tool_path.name == "stabletoolbench.tool_path"
    assert tool_path.kind == "recovered"
    assert tool_path.output["is_successful"] is False
    assert tool_path.output["tool_path"] == ["calculator"]
    assert tool_path.output["tool_argument_keys"] == [["expression"]]
    assert tool_path.output["response_count"] == 1
    assert tool_path.output["malformed_answer_step_count"] == 1

    declared_drops = {
        (drop.reason, drop.dropped_field_path) for drop in win.drops + tool_path.drops
    }
    assert ("trusts_source_evaluator_statuses_without_regrading", "evaluator") in declared_drops
    assert ("skipped_malformed_answer_step_members", "answer_steps[]") in declared_drops


def write_stabletoolbench_fixture(tmp_path: Path) -> Path:
    source_path = tmp_path / "stabletoolbench.jsonl"
    source_path.write_text("\n".join(json.dumps(record) for record in stabletoolbench_records()))
    return source_path


def stabletoolbench_records() -> list[dict]:
    return [
        {
            "trajectory_id": "traj-001",
            "task_id": "task-alpha",
            "question": "Find the weather in London.",
            "answer_steps": [
                {
                    "tool": "search",
                    "arguments": {"query": "weather in London"},
                    "response": {"results": ["rain forecast"]},
                    "status": "ok",
                },
                {
                    "tool_name": "lookup_weather",
                    "args": {"city": "London"},
                    "response": "rain",
                    "status": "ok",
                },
            ],
            "is_solved": True,
            "win": True,
            "evaluator": {"status": "passed"},
        },
        {
            "trajectory_id": "traj-002",
            "task_id": "task-beta",
            "answer_steps": [
                {
                    "name": "calculator",
                    "arguments": {"expression": "2 + 2"},
                    "response": "5",
                    "status": "error",
                },
                "bad-step",
            ],
            "pass": False,
            "evaluator_statuses": ["failed"],
        },
    ]
