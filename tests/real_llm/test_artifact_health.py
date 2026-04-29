import importlib.util
import json
from pathlib import Path

_ARTIFACT_HEALTH_PATH = Path(__file__).with_name("artifact_health.py")
_SPEC = importlib.util.spec_from_file_location("artifact_health", _ARTIFACT_HEALTH_PATH)
assert _SPEC is not None
assert _SPEC.loader is not None
artifact_health = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(artifact_health)
analyze_rollout_artifacts = artifact_health.analyze_rollout_artifacts


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row) for row in rows))


def test_artifact_health_reports_tool_budget_signals(tmp_path: Path) -> None:
    db_dir = tmp_path / "db"
    db_dir.mkdir()
    for name in [
        "run_task_executions.jsonl",
        "run_task_evaluations.jsonl",
        "run_resources.jsonl",
        "run_graph_nodes.jsonl",
    ]:
        (db_dir / name).write_text("")
    _write_jsonl(
        db_dir / "run_context_events.jsonl",
        [
            {
                "event_type": "tool_call",
                "payload": {"event_type": "tool_call", "tool_name": "workflow"},
            },
            {
                "event_type": "tool_call",
                "payload": {"event_type": "tool_call", "tool_name": "exa_search"},
            },
            {
                "event_type": "tool_result",
                "payload": {
                    "event_type": "tool_result",
                    "content": {
                        "status": "TOOL_BUDGET_EXHAUSTED",
                        "reason": "non-workflow tool budget reached",
                    },
                },
            },
        ],
    )

    health = analyze_rollout_artifacts(tmp_path)

    assert health.workflow_tool_calls == 1
    assert health.other_tool_calls == 1
    assert health.budget_exhausted is True
    assert health.missing_final_report is True
