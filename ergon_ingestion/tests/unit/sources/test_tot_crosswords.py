import importlib
import json
from pathlib import Path

import pytest

from ergon_ingestion.models import ImportSource


def test_tot_crosswords_importer_parses_paired_policy_traces(tmp_path: Path) -> None:
    tot_module = _load_tot_crosswords_module()
    source_path = tmp_path / "tot_crosswords.json"
    fixture = {
        "traces": [
            {
                "puzzle_id": "mini-cw-001",
                "policy": "dfs_prune",
                "final_reward": 1.0,
                "actions": ["fill 1A CAT", "fill 2D TEA", "submit"],
                "states": [
                    {"state_id": "root", "depth": 0, "filled": 0},
                    {"state_id": "s1", "depth": 1, "filled": 1},
                    {"state_id": "s2", "depth": 2, "filled": 2},
                ],
                "search": {
                    "visited_states": 3,
                    "max_depth": 2,
                    "backtracks": 0,
                    "coverage": 1.0,
                },
            },
            {
                "puzzle_id": "mini-cw-001",
                "policy": "dfs_no_prune",
                "final_reward": 0.5,
                "actions": ["fill 1A CAR", "backtrack 1A", "fill 1A CAT", "submit"],
                "states": [
                    {"state_id": "root", "depth": 0, "filled": 0},
                    {"state_id": "dead-end", "depth": 1, "filled": 1},
                    {"state_id": "retry", "depth": 1, "filled": 1},
                    {"state_id": "partial", "depth": 2, "filled": 2},
                ],
                "search": {
                    "visited_states": 4,
                    "max_depth": 2,
                    "backtracks": 1,
                    "coverage": 0.75,
                },
            },
        ]
    }
    source_path.write_text(json.dumps(fixture))

    importer = tot_module.TotCrosswordsImporter()
    source = ImportSource(
        dataset="tot_crosswords",
        input_path=source_path,
        batch_id="tot-crosswords-unit",
    )
    report = importer.validate(source)
    runs = list(importer.iter_runs(source))

    assert report.ok is True
    assert report.planned_runs == 2
    assert len(runs) == 2
    assert {run.instance_key for run in runs} == {"mini-cw-001"}

    prune_run = one_by_source_run_id(runs, "mini-cw-001:dfs_prune")
    no_prune_run = one_by_source_run_id(runs, "mini-cw-001:dfs_no_prune")
    assert prune_run.schema_fit_class == "full-trace"
    assert no_prune_run.schema_fit_class == "full-trace"

    assert [event.event_type for event in prune_run.events] == [
        "tot.action",
        "tot.action",
        "tot.action",
        "tot.state",
        "tot.state",
        "tot.state",
    ]
    assert prune_run.events[0].payload == {"action": "fill 1A CAT", "policy": "dfs_prune"}
    assert prune_run.events[-1].payload == {
        "state_id": "s2",
        "depth": 2,
        "filled": 2,
        "policy": "dfs_prune",
    }
    trace_resource = one_by_name(prune_run.resources, "tot-trace.json")
    assert trace_resource.payload == fixture["traces"][0]
    search_annotation = one_by_namespace(prune_run.annotations, "tot.search_shape")
    assert search_annotation.payload == {
        "policy": "dfs_prune",
        "visited_states": 3,
        "action_count": 3,
        "unique_atomic_actions": 3,
        "max_depth": 2,
        "backtracks": 0,
        "coverage": 1.0,
    }

    reducers = {reducer.name: reducer for reducer in no_prune_run.reducers}
    assert set(reducers) == {"tot.final_reward", "tot.search_efficiency"}
    assert reducers["tot.final_reward"].output == {"final_reward": 0.5}
    assert reducers["tot.final_reward"].fields_read == ["final_reward"]
    assert reducers["tot.search_efficiency"].output == {
        "visited_states": 4,
        "action_count": 4,
        "unique_atomic_actions": 4,
        "max_depth": 2,
        "backtracks": 1,
        "coverage": 0.75,
        "reward_per_visited_state": 0.125,
    }
    assert reducers["tot.search_efficiency"].fields_read == [
        "actions",
        "states",
        "search.visited_states",
        "search.max_depth",
        "search.backtracks",
        "search.coverage",
        "final_reward",
    ]
    dropped_paths = {
        drop.dropped_field_path
        for reducer in reducers.values()
        for drop in reducer.drops
    }
    assert {
        "evaluator.value_estimates",
        "pruning.branch_scores",
        "pruning.hidden_thresholds",
    }.issubset(dropped_paths)
    assert no_prune_run.missing_fields == [
        "evaluator.value_estimates",
        "pruning.branch_scores",
        "pruning.hidden_thresholds",
    ]


def _load_tot_crosswords_module():
    try:
        return importlib.import_module("ergon_ingestion.sources.tot_crosswords")
    except ModuleNotFoundError as exc:
        pytest.fail(f"ToT crosswords source parser is not implemented: {exc}")


def one_by_source_run_id(runs, source_run_id: str):
    matches = [run for run in runs if run.source_run_id == source_run_id]
    assert len(matches) == 1
    return matches[0]


def one_by_namespace(annotations, namespace: str):
    matches = [annotation for annotation in annotations if annotation.namespace == namespace]
    assert len(matches) == 1
    return matches[0]


def one_by_name(resources, name: str):
    matches = [resource for resource in resources if resource.name == name]
    assert len(matches) == 1
    return matches[0]
