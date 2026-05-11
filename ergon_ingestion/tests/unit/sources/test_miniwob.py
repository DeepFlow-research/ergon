import gzip
import json
from pathlib import Path

from ergon_ingestion.models import ImportSource
from ergon_ingestion.reducers.miniwob import action_path_reducer, success_reducer
from ergon_ingestion.sources.miniwob import MiniWobImporter, parse_miniwob_record


VALID_RESOURCE_KINDS = {"import", "artifact", "report", "output", "search_cache", "note"}


def test_parse_miniwob_record_preserves_trace_events_resources_and_caveats() -> None:
    record = miniwob_record()

    run = parse_miniwob_record(record)

    assert run.source_run_id == "episode-001"
    assert run.instance_key == "click-button"
    assert run.schema_fit_class == "full-trace"
    assert run.observed_fields["episode_id"] == "episode-001"
    assert run.observed_fields["task_id"] == "click-button"
    assert run.observed_fields["instruction"] == "Click the green submit button."
    assert run.observed_fields["reward"] == 1.0
    assert run.observed_fields["success"] is True
    assert [event.event_type for event in run.events] == [
        "instruction",
        "ui_action.click",
        "ui_action.type",
        "ui_action.key",
    ]
    assert run.events[0].payload == {"instruction": "Click the green submit button."}
    assert run.events[1].payload["target"] == {"ref": "button.green-submit"}
    assert run.events[2].payload["text"] == "done"
    assert {resource.kind for resource in run.resources}.issubset(VALID_RESOURCE_KINDS)
    assert {resource.name for resource in run.resources} == {
        "source-record.json",
        "instruction.json",
        "actions.json",
        "external-ui-artifacts.json",
    }

    reducers = {reducer.name: reducer for reducer in run.reducers}
    assert set(reducers) == {"miniwob.success", "miniwob.action_path"}
    assert reducers["miniwob.success"].fields_read == ["success", "reward", "outcome"]
    assert reducers["miniwob.success"].output == {
        "success": True,
        "reward": 1.0,
        "outcome": "success",
    }
    assert reducers["miniwob.action_path"].fields_read == ["actions", "instruction", "utterance"]
    assert reducers["miniwob.action_path"].output == {
        "instruction": "Click the green submit button.",
        "action_count": 3,
        "action_names": ["click", "type", "key"],
        "target_refs": ["button.green-submit", "input.answer", None],
        "typed_text": ["done"],
        "key_events": ["ENTER"],
    }

    all_drops = run.missing_fields + [
        drop.dropped_field_path or "" for reducer in run.reducers for drop in reducer.drops
    ]
    assert any("dom" in field.lower() for field in all_drops)
    assert any("screenshot" in field.lower() for field in all_drops)
    assert any("replay" in field.lower() for field in all_drops)


def test_miniwob_importer_reads_json_and_json_gz_records(tmp_path: Path) -> None:
    json_path = tmp_path / "miniwob.json"
    json_path.write_text(
        json.dumps([miniwob_record("episode-json-1"), miniwob_record("episode-json-2")])
    )
    gz_path = tmp_path / "miniwob.json.gz"
    with gzip.open(gz_path, "wt") as handle:
        json.dump(miniwob_record("episode-gz"), handle)

    importer = MiniWobImporter()
    json_source = ImportSource(dataset="miniwob", input_path=json_path, batch_id="miniwob-unit")
    gz_source = ImportSource(dataset="miniwob", input_path=gz_path, batch_id="miniwob-unit")

    assert importer.validate(json_source).planned_runs == 2
    assert [run.source_run_id for run in importer.iter_runs(json_source)] == [
        "episode-json-1",
        "episode-json-2",
    ]
    assert importer.validate(gz_source).planned_runs == 1
    gz_run = next(importer.iter_runs(gz_source))
    assert gz_run.source_run_id == "episode-gz"
    assert gz_run.resources[0].kind == "import"


def test_miniwob_reducers_read_outcome_action_fields_and_declare_caveats() -> None:
    record = miniwob_record()

    success = success_reducer(record)
    action_path = action_path_reducer(record)

    assert success.name == "miniwob.success"
    assert success.kind == "original"
    assert success.fields_read == ["success", "reward", "outcome"]
    assert action_path.name == "miniwob.action_path"
    assert action_path.kind == "recovered"
    assert action_path.fields_read == ["actions", "instruction", "utterance"]
    assert action_path.output["action_names"] == ["click", "type", "key"]

    declared_drops = {
        (drop.reason, drop.dropped_field_path) for drop in success.drops + action_path.drops
    }
    assert (
        "dom_state_is_referenced_but_not_imported_as_bytes",
        "dom/state",
    ) in declared_drops
    assert (
        "screenshots_are_referenced_but_not_imported_as_bytes",
        "screenshots",
    ) in declared_drops
    assert (
        "miniwob_replay_environment_is_not_available_during_import",
        "replay_environment",
    ) in declared_drops


def miniwob_record(episode_id: str = "episode-001") -> dict[str, object]:
    return {
        "episode_id": episode_id,
        "task_id": "click-button",
        "instruction": "Click the green submit button.",
        "actions": [
            {
                "type": "click",
                "target": {"ref": "button.green-submit"},
                "x": 42,
                "y": 9,
                "dom_ref": "file://miniwob/dom/episode-001/0001.html",
                "screenshot_ref": "file://miniwob/screens/episode-001/0001.png",
            },
            {
                "action": "type",
                "target_ref": "input.answer",
                "text": "done",
                "state_ref": "file://miniwob/state/episode-001/0002.json",
            },
            {"type": "key", "key": "ENTER"},
        ],
        "reward": 1.0,
        "success": True,
        "outcome": "success",
        "dom_ref": "file://miniwob/dom/episode-001/final.html",
        "state_ref": "file://miniwob/state/episode-001/final.json",
        "screenshot_ref": "file://miniwob/screens/episode-001/final.png",
    }
