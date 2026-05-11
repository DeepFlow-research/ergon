import importlib
import json
from pathlib import Path

import pytest

from ergon_ingestion.models import ImportSource


VALID_RESOURCE_KINDS = {"import", "artifact", "report", "output", "search_cache", "note"}


def test_agent_reward_bench_importer_preserves_reward_labels_process_trace_and_caveats(
    tmp_path: Path,
) -> None:
    source_module = _load_source_module()
    source_path = write_agent_reward_bench_fixture(tmp_path)
    importer = source_module.AgentRewardBenchImporter()

    runs = list(
        importer.iter_runs(
            ImportSource(
                dataset="agent_reward_bench",
                input_path=source_path,
                batch_id="agent-reward-bench-unit",
            )
        )
    )

    assert len(runs) == 1
    run = runs[0]
    assert run.source_run_id == "arb-trajectory-1"
    assert run.instance_key == "task-42"
    assert run.schema_fit_class == "full-trace"
    assert run.observed_fields["trajectory_id"] == "arb-trajectory-1"
    assert run.observed_fields["task_id"] == "task-42"
    assert run.observed_fields["reward_score"] == 0.82
    assert run.observed_fields["preference_label"] == "chosen"
    assert run.observed_fields["judge"] == {"model": "judge-v1", "rubric": "task-success"}
    assert run.observed_fields["annotator"] == {"id": "ann-7", "type": "human"}
    assert "independent_rejudge" in run.missing_fields
    assert "inter_annotator_agreement" in run.missing_fields

    assert [event.event_type for event in run.events] == [
        "message.user",
        "message.assistant",
        "tool_call",
        "action",
        "tool_result",
        "message.assistant",
    ]
    assert run.events[2].payload == {
        "id": "call-weather",
        "name": "weather.search",
        "args": {"city": "London"},
        "message_index": 1,
    }
    assert run.events[3].payload == {
        "name": "weather.search",
        "order": 0,
        "tool_call_id": "call-weather",
        "arguments": {"city": "London"},
        "reward_delta": 0.4,
    }

    resources = {resource.name: resource for resource in run.resources}
    assert {resource.kind for resource in run.resources} <= VALID_RESOURCE_KINDS
    assert resources["source-record.json"].kind == "import"
    assert resources["messages.json"].payload["messages"][1]["tool_calls"][0]["name"] == (
        "weather.search"
    )
    assert resources["actions.json"].payload["actions"][0]["reward_delta"] == 0.4
    assert resources["tool-calls.json"].payload == {
        "tool_calls": [{"id": "call-weather", "name": "weather.search", "args": {"city": "London"}}]
    }

    reducers = {reducer.name: reducer for reducer in run.reducers}
    assert set(reducers) == {
        "agent_reward_bench.reward_label",
        "agent_reward_bench.process_trace",
    }
    assert reducers["agent_reward_bench.reward_label"].fields_read == [
        "reward_score",
        "preference_label",
        "judge",
        "annotator",
        "annotation_metadata",
    ]
    assert reducers["agent_reward_bench.reward_label"].output == {
        "reward_score": 0.82,
        "preference_label": "chosen",
        "judge": {"model": "judge-v1", "rubric": "task-success"},
        "annotator": {"id": "ann-7", "type": "human"},
        "annotation_metadata": {"guidelines_version": "2026-04"},
    }
    assert reducers["agent_reward_bench.process_trace"].fields_read == [
        "messages",
        "actions",
        "tool_calls",
        "process_trace",
        "reward_score",
        "preference_label",
    ]
    assert reducers["agent_reward_bench.process_trace"].output == {
        "message_count": 4,
        "action_count": 1,
        "tool_call_count": 1,
        "tool_names": ["weather.search"],
        "process_trace": [{"step": "search", "rationale": "Needed live weather."}],
        "reward_score": 0.82,
        "preference_label": "chosen",
    }

    declared_caveats = {
        (drop.reason, drop.dropped_field_path) for reducer in run.reducers for drop in reducer.drops
    }
    assert ("missing_independent_rejudge_provenance", "independent_rejudge") in declared_caveats
    assert (
        "missing_inter_annotator_provenance",
        "inter_annotator_agreement",
    ) in declared_caveats


def test_agent_reward_bench_reducers_read_reward_preference_and_process_fields() -> None:
    reducers_module = _load_reducers_module()
    record = agent_reward_bench_records()[0]

    reward = reducers_module.reward_label_reducer(record)
    process = reducers_module.process_trace_reducer(record)

    assert reward.name == "agent_reward_bench.reward_label"
    assert reward.fields_read == [
        "reward_score",
        "preference_label",
        "judge",
        "annotator",
        "annotation_metadata",
    ]
    assert reward.output["reward_score"] == 0.82
    assert reward.output["preference_label"] == "chosen"

    assert process.name == "agent_reward_bench.process_trace"
    assert process.fields_read == [
        "messages",
        "actions",
        "tool_calls",
        "process_trace",
        "reward_score",
        "preference_label",
    ]
    assert process.output["tool_names"] == ["weather.search"]
    assert process.output["process_trace"] == [
        {"step": "search", "rationale": "Needed live weather."}
    ]

    caveats = {
        (drop.reason, drop.dropped_field_path)
        for reducer in [reward, process]
        for drop in reducer.drops
    }
    assert ("missing_independent_rejudge_provenance", "independent_rejudge") in caveats
    assert ("missing_inter_annotator_provenance", "inter_annotator_agreement") in caveats


def write_agent_reward_bench_fixture(tmp_path: Path) -> Path:
    source_path = tmp_path / "agent_reward_bench.jsonl"
    source_path.write_text("\n".join(json.dumps(record) for record in agent_reward_bench_records()))
    return source_path


def agent_reward_bench_records() -> list[dict]:
    return [
        {
            "trajectory_id": "arb-trajectory-1",
            "task_id": "task-42",
            "messages": [
                {"role": "user", "content": "Should I carry an umbrella in London today?"},
                {
                    "role": "assistant",
                    "content": "I will check the weather.",
                    "tool_calls": [
                        {
                            "id": "call-weather",
                            "name": "weather.search",
                            "args": {"city": "London"},
                        }
                    ],
                },
                {
                    "role": "tool",
                    "tool_call_id": "call-weather",
                    "name": "weather.search",
                    "content": {"forecast": "rain"},
                },
                {"role": "assistant", "content": "Yes, rain is expected."},
            ],
            "actions": [
                {
                    "name": "weather.search",
                    "tool_call_id": "call-weather",
                    "arguments": {"city": "London"},
                    "reward_delta": 0.4,
                }
            ],
            "tool_calls": [
                {"id": "call-weather", "name": "weather.search", "args": {"city": "London"}}
            ],
            "process_trace": [{"step": "search", "rationale": "Needed live weather."}],
            "reward_score": 0.82,
            "preference_label": "chosen",
            "judge": {"model": "judge-v1", "rubric": "task-success"},
            "annotator": {"id": "ann-7", "type": "human"},
            "annotation_metadata": {"guidelines_version": "2026-04"},
        }
    ]


def _load_source_module():
    try:
        return importlib.import_module("ergon_ingestion.sources.agent_reward_bench")
    except ModuleNotFoundError as exc:
        pytest.fail(f"Agent Reward Bench source parser is not implemented: {exc}")


def _load_reducers_module():
    try:
        return importlib.import_module("ergon_ingestion.reducers.agent_reward_bench")
    except ModuleNotFoundError as exc:
        pytest.fail(f"Agent Reward Bench reducers are not implemented: {exc}")
