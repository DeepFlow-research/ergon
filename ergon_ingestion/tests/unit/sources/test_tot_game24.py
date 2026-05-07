import importlib
import json
from pathlib import Path

import pytest

from ergon_ingestion.models import ImportSource


def test_tot_game24_importer_parses_search_trace_records(tmp_path: Path) -> None:
    tot_module = _load_tot_game24_module()
    source_path = tmp_path / "tot_game24.json"
    fixture = {
        "traces": [
            {
                "puzzle_id": "game24-001",
                "numbers": [4, 7, 8, 8],
                "steps": [
                    {
                        "depth": 0,
                        "thought": "Try pairing 8 and 4 first.",
                        "action": "8 - 4 = 4",
                        "value": "likely",
                        "info": {"correct": False},
                    },
                    {
                        "depth": 1,
                        "thought": "Use the remaining 7 with the derived 4.",
                        "action": "7 - 4 = 3",
                        "value": "sure",
                        "info": {"correct": True},
                    },
                ],
                "actions": ["8 - 4 = 4", "7 - 4 = 3", "8 * 3 = 24"],
                "values": ["likely", "sure", "sure"],
                "infos": [{"correct": False}, {"correct": True}, {"correct": True}],
                "final_answer": "(8 - 4) * (7 - 1)",
                "final_reward": 1.0,
            },
            {
                "puzzle_id": "game24-002",
                "numbers": "1 3 4 6",
                "steps": [{"thought": "6 / (1 - 3 / 4)", "value": "sure", "correct": True}],
                "actions": [{"expression": "6 / (1 - 3 / 4)"}],
                "values": [{"value": "sure", "score": 1.0}],
                "correctness": [True],
                "final_answer": "6 / (1 - 3 / 4)",
                "final_reward": 1,
            },
        ]
    }
    source_path.write_text(json.dumps(fixture))

    importer = tot_module.TotGame24Importer()
    source = ImportSource(
        dataset="tot_game24",
        input_path=source_path,
        batch_id="tot-game24-unit",
    )
    report = importer.validate(source)
    runs = list(importer.iter_runs(source))

    assert report.ok is True
    assert report.planned_runs == 2
    assert [run.source_run_id for run in runs] == ["game24-001", "game24-002"]

    run = runs[0]
    assert run.instance_key == "game24-001"
    assert run.schema_fit_class == "full-trace"
    assert run.observed_fields == fixture["traces"][0]
    assert run.missing_fields == [
        "steps[].branch_id",
        "evaluator.internal_value_model",
        "evaluator.prompt_transcripts",
    ]

    assert [event.event_type for event in run.events] == [
        "tot.game24.step",
        "tot.game24.step",
        "tot.game24.action",
        "tot.game24.action",
        "tot.game24.action",
        "tot.game24.value",
        "tot.game24.value",
        "tot.game24.value",
        "tot.game24.info",
        "tot.game24.info",
        "tot.game24.info",
    ]
    assert run.events[0].payload == {
        "depth": 0,
        "thought": "Try pairing 8 and 4 first.",
        "action": "8 - 4 = 4",
        "value": "likely",
        "info": {"correct": False},
        "puzzle_id": "game24-001",
    }
    assert run.events[2].payload == {"action": "8 - 4 = 4", "puzzle_id": "game24-001"}
    assert run.events[-1].payload == {"correct": True, "puzzle_id": "game24-001"}

    trace_resource = one_by_name(run.resources, "tot-game24-trace.json")
    assert trace_resource.kind == "artifact"
    assert trace_resource.payload == fixture["traces"][0]

    reducers = {reducer.name: reducer for reducer in run.reducers}
    assert set(reducers) == {"tot.game24_final_answer", "tot.game24_value_trace"}
    assert reducers["tot.game24_final_answer"].output == {
        "numbers": [4, 7, 8, 8],
        "final_answer": "(8 - 4) * (7 - 1)",
        "final_reward": 1.0,
        "source_correct": True,
    }
    assert reducers["tot.game24_final_answer"].fields_read == [
        "numbers",
        "final_answer",
        "final_reward",
        "infos",
        "correctness",
    ]
    assert reducers["tot.game24_value_trace"].output == {
        "step_count": 2,
        "action_count": 3,
        "value_count": 3,
        "info_count": 3,
        "values": ["likely", "sure", "sure"],
        "source_correct_count": 2,
    }
    assert reducers["tot.game24_value_trace"].fields_read == [
        "steps",
        "actions",
        "values",
        "infos",
        "correctness",
    ]

    dropped_paths = {
        drop.dropped_field_path for reducer in reducers.values() for drop in reducer.drops
    }
    assert {
        "steps[].branch_id",
        "evaluator.internal_value_model",
        "evaluator.prompt_transcripts",
        "infos[].correct",
    }.issubset(dropped_paths)


def _load_tot_game24_module():
    try:
        return importlib.import_module("ergon_ingestion.sources.tot_game24")
    except ModuleNotFoundError as exc:
        pytest.fail(f"ToT Game24 source parser is not implemented: {exc}")


def one_by_name(resources, name: str):
    matches = [resource for resource in resources if resource.name == name]
    assert len(matches) == 1
    return matches[0]
