import gzip
import json
from pathlib import Path

from ergon_ingestion.models import ImportSource
from ergon_ingestion.sources.weblinx import WebLinxImporter, parse_weblinx_record


VALID_RESOURCE_KINDS = {"import", "artifact", "report", "output", "search_cache", "note"}


def test_parse_weblinx_record_preserves_trace_events_resources_and_caveats() -> None:
    record = _record()

    run = parse_weblinx_record(record)

    assert run.source_run_id == "demo-001"
    assert run.instance_key == "session-abc"
    assert run.schema_fit_class == "full-trace"
    assert run.observed_fields == {
        "demo_id": "demo-001",
        "session_id": "session-abc",
        "success": True,
        "outcome": "success",
    }
    assert {event.event_type for event in run.events} == {
        "utterance.user",
        "utterance.assistant",
        "browser_action.click",
        "browser_action.type",
        "browser_action.navigate",
    }
    assert run.events[2].payload["target"] == {"backend_node_id": "node-42", "label": "Search"}
    assert {resource.kind for resource in run.resources}.issubset(VALID_RESOURCE_KINDS)
    assert {resource.name for resource in run.resources} == {
        "source-record.json",
        "utterances.json",
        "actions.json",
        "external-browser-artifacts.json",
    }

    reducers = {reducer.name: reducer for reducer in run.reducers}
    assert set(reducers) == {"weblinx.success", "weblinx.action_path"}
    assert reducers["weblinx.success"].fields_read == ["success", "outcome", "eval"]
    assert reducers["weblinx.action_path"].fields_read == ["actions", "utterances", "messages"]
    assert reducers["weblinx.action_path"].output["action_names"] == ["click", "type", "navigate"]
    assert reducers["weblinx.action_path"].output["utterance_roles"] == ["user", "assistant"]

    all_drops = run.missing_fields + [
        drop.dropped_field_path or "" for reducer in run.reducers for drop in reducer.drops
    ]
    assert any("dom" in field.lower() for field in all_drops)
    assert any("screenshot" in field.lower() for field in all_drops)
    assert any("replay" in field.lower() for field in all_drops)


def test_weblinx_importer_reads_json_and_json_gz_records(tmp_path: Path) -> None:
    json_path = tmp_path / "weblinx.json"
    json_path.write_text(json.dumps([_record("demo-json"), _record("demo-json-2")]))
    gz_path = tmp_path / "weblinx.json.gz"
    with gzip.open(gz_path, "wt") as handle:
        json.dump(_record("demo-gz"), handle)

    importer = WebLinxImporter()

    json_source = ImportSource(dataset="weblinx", input_path=json_path, batch_id="unit")
    gz_source = ImportSource(dataset="weblinx", input_path=gz_path, batch_id="unit")

    assert importer.validate(json_source).planned_runs == 2
    assert [run.source_run_id for run in importer.iter_runs(json_source)] == [
        "demo-json",
        "demo-json-2",
    ]
    assert importer.validate(gz_source).planned_runs == 1
    gz_run = next(importer.iter_runs(gz_source))
    assert gz_run.source_run_id == "demo-gz"
    assert gz_run.resources[0].kind == "import"


def _record(demo_id: str = "demo-001") -> dict[str, object]:
    return {
        "demo_id": demo_id,
        "session_id": "session-abc",
        "utterances": [
            {"role": "user", "text": "Find the docs"},
            {"role": "assistant", "text": "Opening the search page"},
        ],
        "actions": [
            {
                "type": "click",
                "target": {"backend_node_id": "node-42", "label": "Search"},
                "dom_ref": "s3://weblinx/dom/demo-001/0001.html",
                "screenshot_ref": "s3://weblinx/screens/demo-001/0001.png",
            },
            {"type": "type", "target": {"backend_node_id": "node-43"}, "text": "docs"},
            {"type": "navigate", "url": "https://example.test/docs"},
        ],
        "success": True,
        "outcome": "success",
        "eval": {"label": "success"},
        "dom_snapshot_ref": "s3://weblinx/dom/demo-001/final.html",
        "screenshot_ref": "s3://weblinx/screens/demo-001/final.png",
    }
