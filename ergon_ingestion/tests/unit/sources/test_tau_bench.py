import json
from pathlib import Path

from ergon_ingestion.models import ImportSource
from ergon_ingestion.reducers.tau_bench import (
    reduce_db_state,
    reduce_reward,
    reduce_sequence,
    reduce_set,
)
from ergon_ingestion.sources.tau_bench import TauBenchImporter


def test_tau_bench_importer_preserves_full_trace_events_resources_and_reducers(
    tmp_path: Path,
) -> None:
    source_path = write_tau_bench_fixture(tmp_path)
    importer = TauBenchImporter()

    runs = list(
        importer.iter_runs(
            ImportSource(dataset="tau_bench", input_path=source_path, batch_id="paper-rq2")
        )
    )

    assert [run.source_run_id for run in runs] == ["airline:refund-001", "retail:return-002"]
    assert [run.schema_fit_class for run in runs] == ["full-trace", "full-trace"]
    assert runs[0].instance_key == "airline:refund-001"
    assert runs[0].observed_fields["domain"] == "airline"
    assert runs[0].observed_fields["task_id"] == "refund-001"
    assert runs[0].observed_fields["success"] is True

    assert [event.event_type for event in runs[0].events] == [
        "message.system",
        "message.user",
        "message.assistant",
        "tool_call",
        "tool_result",
    ]
    assert runs[0].events[3].payload == {
        "id": "call-1",
        "name": "update_ticket",
        "args": {"ticket_id": "T-1", "status": "refunded"},
        "message_index": 2,
    }
    assert runs[0].resources[0].name == "source-record.json"
    assert runs[0].resources[0].payload["messages"][2]["tool_calls"][0]["name"] == (
        "update_ticket"
    )
    assert runs[0].resources[1].name == "final-state.json"
    assert runs[0].resources[1].payload == {"ticket": {"id": "T-1", "status": "refunded"}}

    reducers = {reducer.name: reducer for reducer in runs[0].reducers}
    assert set(reducers) == {
        "tau_bench.reward",
        "tau_bench.db_state",
        "tau_bench.sequence",
        "tau_bench.set",
    }
    assert reducers["tau_bench.reward"].fields_read == ["reward", "success"]
    assert reducers["tau_bench.db_state"].fields_read == ["final_state"]
    assert reducers["tau_bench.sequence"].fields_read == ["messages"]
    assert reducers["tau_bench.set"].fields_read == ["messages"]
    assert reducers["tau_bench.reward"].output == {"reward": 1.0, "success": True}
    assert reducers["tau_bench.db_state"].output == {
        "final_state": {"ticket": {"id": "T-1", "status": "refunded"}}
    }
    assert reducers["tau_bench.sequence"].output["tool_names"] == ["update_ticket"]
    assert reducers["tau_bench.set"].output["tool_names"] == ["update_ticket"]

    drop_reasons = {
        drop.reason
        for reducer in runs[0].reducers
        for drop in reducer.drops
    }
    assert "autonomy_and_user_turn_attribution_not_separable_from_trace" in drop_reasons
    assert "environment_internals_unavailable_beyond_final_state" in drop_reasons


def test_tau_bench_reducers_declare_fields_read_and_missing_caveats() -> None:
    record = tau_bench_records()[1]

    reward = reduce_reward(record)
    db_state = reduce_db_state(record)
    sequence = reduce_sequence(record)
    tool_set = reduce_set(record)

    assert reward.name == "tau_bench.reward"
    assert reward.fields_read == ["reward", "success"]
    assert reward.output == {"reward": 0.0, "success": False}

    assert db_state.name == "tau_bench.db_state"
    assert db_state.fields_read == ["final_state"]
    assert db_state.output == {"final_state": {"order": {"id": "O-2", "status": "pending"}}}

    assert sequence.name == "tau_bench.sequence"
    assert sequence.fields_read == ["messages"]
    assert sequence.output["roles"] == ["user", "assistant", "tool", "assistant"]
    assert sequence.output["tool_names"] == ["lookup_order"]

    assert tool_set.name == "tau_bench.set"
    assert tool_set.fields_read == ["messages"]
    assert tool_set.output == {"tool_names": ["lookup_order"], "tool_result_names": ["lookup_order"]}

    declared_missing = {
        drop.dropped_field_path
        for reducer in [reward, db_state, sequence, tool_set]
        for drop in reducer.drops
    }
    assert "autonomy.user_turn_contribution" in declared_missing
    assert "environment.internal_state_transitions" in declared_missing


def write_tau_bench_fixture(tmp_path: Path) -> Path:
    source_path = tmp_path / "tau_bench.jsonl"
    source_path.write_text("\n".join(json.dumps(record) for record in tau_bench_records()))
    return source_path


def tau_bench_records() -> list[dict]:
    return [
        {
            "domain": "airline",
            "task_id": "refund-001",
            "reward": 1.0,
            "success": True,
            "messages": [
                {"role": "system", "content": "Follow airline policy."},
                {"role": "user", "content": "Refund ticket T-1."},
                {
                    "role": "assistant",
                    "content": "I will update the ticket.",
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "name": "update_ticket",
                            "args": {"ticket_id": "T-1", "status": "refunded"},
                        }
                    ],
                },
                {
                    "role": "tool",
                    "tool_call_id": "call-1",
                    "name": "update_ticket",
                    "content": {"ok": True},
                },
            ],
            "final_state": {"ticket": {"id": "T-1", "status": "refunded"}},
        },
        {
            "domain": "retail",
            "task_id": "return-002",
            "reward": 0.0,
            "success": False,
            "messages": [
                {"role": "user", "content": "Return order O-2."},
                {
                    "role": "assistant",
                    "content": "I need to inspect the order first.",
                    "tool_calls": [
                        {
                            "id": "call-2",
                            "name": "lookup_order",
                            "args": {"order_id": "O-2"},
                        }
                    ],
                },
                {
                    "role": "tool",
                    "tool_call_id": "call-2",
                    "name": "lookup_order",
                    "content": {"status": "pending"},
                },
                {"role": "assistant", "content": "The return cannot be completed."},
            ],
            "final_state": {"order": {"id": "O-2", "status": "pending"}},
        },
    ]
