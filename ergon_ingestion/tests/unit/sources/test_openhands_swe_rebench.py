import json
from pathlib import Path

from ergon_ingestion.models import ImportSource
from ergon_ingestion.reducers.openhands_swe_rebench import (
    reduce_patch_trace,
    reduce_resolved,
)
from ergon_ingestion.sources.openhands_swe_rebench import OpenHandsSweRebenchImporter


VALID_RESOURCE_KINDS = {"import", "artifact", "report", "output", "search_cache", "note"}


def test_openhands_swe_rebench_importer_preserves_trace_patch_and_declares_caveats(
    tmp_path: Path,
) -> None:
    source_path = write_openhands_fixture(tmp_path)
    importer = OpenHandsSweRebenchImporter()

    runs = list(
        importer.iter_runs(
            ImportSource(
                dataset="openhands_swe_rebench",
                input_path=source_path,
                batch_id="openhands-unit",
            )
        )
    )

    assert [run.source_run_id for run in runs] == [
        "django__django-12345",
        "sympy__sympy-67890",
    ]
    assert runs[0].instance_key == "django__django-12345"
    assert runs[0].schema_fit_class == "full-trace"
    assert runs[0].observed_fields["repo"] == "django/django"
    assert runs[0].observed_fields["base_commit"] == "abc123"
    assert runs[0].observed_fields["issue"] == "Fix timezone parsing."
    assert runs[0].observed_fields["resolved"] is True
    assert runs[0].observed_fields["eval_status"] == "pass"

    assert [event.event_type for event in runs[0].events] == [
        "message.user",
        "message.assistant",
        "tool_call",
        "action",
        "tool_result",
    ]
    assert runs[0].events[2].payload == {
        "id": "call-1",
        "name": "bash",
        "args": {"cmd": "pytest tests/test_timezones.py"},
        "message_index": 1,
    }
    assert runs[0].events[3].payload == {
        "action_index": 0,
        "action": "edit",
        "path": "django/utils/dateparse.py",
        "tool": "str_replace_editor",
    }

    assert [resource.kind for resource in runs[0].resources] == ["import", "output", "artifact"]
    assert all(resource.kind in VALID_RESOURCE_KINDS for resource in runs[0].resources)
    assert runs[0].resources[0].payload["messages"][1]["tool_calls"][0]["name"] == "bash"
    assert runs[0].resources[1].name == "patch.diff"
    assert runs[0].resources[1].payload == openhands_records()[0]["patch"]
    assert runs[0].resources[2].name == "trace.json"
    assert runs[0].resources[2].payload["actions"] == openhands_records()[0]["actions"]

    reducers = {reducer.name: reducer for reducer in runs[0].reducers}
    assert set(reducers) == {
        "openhands_swe_rebench.resolved",
        "openhands_swe_rebench.patch_trace",
    }
    assert reducers["openhands_swe_rebench.resolved"].fields_read == [
        "resolved",
        "eval_status",
        "pass",
        "test_status",
    ]
    assert reducers["openhands_swe_rebench.resolved"].output == {
        "resolved": True,
        "eval_status": "pass",
        "pass": None,
        "test_status": "passed",
    }
    assert reducers["openhands_swe_rebench.patch_trace"].fields_read == [
        "patch",
        "messages",
        "actions",
        "tool_calls",
        "resolved",
        "eval_status",
    ]
    assert reducers["openhands_swe_rebench.patch_trace"].output == {
        "resolved": True,
        "eval_status": "pass",
        "patch_line_count": 5,
        "patch_added_lines": 1,
        "patch_removed_lines": 1,
        "message_count": 3,
        "action_count": 1,
        "tool_call_count": 1,
        "tool_names": ["bash"],
        "touched_files": ["django/utils/dateparse.py"],
    }

    drop_reasons = {drop.reason for reducer in runs[0].reducers for drop in reducer.drops}
    assert "evaluator_environment_and_tests_not_reproduced" in drop_reasons


def test_openhands_swe_rebench_reducers_read_outcome_patch_trace_and_declare_drops() -> None:
    record = openhands_records()[1]

    resolved = reduce_resolved(record)
    patch_trace = reduce_patch_trace(record)

    assert resolved.name == "openhands_swe_rebench.resolved"
    assert resolved.kind == "original"
    assert resolved.fields_read == ["resolved", "eval_status", "pass", "test_status"]
    assert resolved.output == {
        "resolved": False,
        "eval_status": "fail",
        "pass": False,
        "test_status": None,
    }

    assert patch_trace.name == "openhands_swe_rebench.patch_trace"
    assert patch_trace.kind == "recovered"
    assert patch_trace.output["patch_line_count"] == 4
    assert patch_trace.output["patch_added_lines"] == 1
    assert patch_trace.output["patch_removed_lines"] == 0
    assert patch_trace.output["message_count"] == 2
    assert patch_trace.output["action_count"] == 1
    assert patch_trace.output["tool_call_count"] == 1
    assert patch_trace.output["tool_names"] == ["python"]
    assert patch_trace.output["touched_files"] == ["sympy/printing/str.py"]

    declared_drops = {
        (drop.reason, drop.dropped_field_path)
        for reducer in [resolved, patch_trace]
        for drop in reducer.drops
    }
    assert (
        "evaluator_environment_and_tests_not_reproduced",
        "evaluation.environment",
    ) in declared_drops
    assert (
        "evaluator_environment_and_tests_not_reproduced",
        "evaluation.tests",
    ) in declared_drops


def write_openhands_fixture(tmp_path: Path) -> Path:
    source_path = tmp_path / "openhands_swe_rebench.jsonl"
    source_path.write_text("\n".join(json.dumps(record) for record in openhands_records()))
    return source_path


def openhands_records() -> list[dict]:
    return [
        {
            "instance_id": "django__django-12345",
            "repo": "django/django",
            "base_commit": "abc123",
            "issue": "Fix timezone parsing.",
            "messages": [
                {"role": "user", "content": "Please fix the timezone parser."},
                {
                    "role": "assistant",
                    "content": "I will run the focused tests.",
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "name": "bash",
                            "args": {"cmd": "pytest tests/test_timezones.py"},
                        }
                    ],
                },
                {
                    "role": "tool",
                    "tool_call_id": "call-1",
                    "name": "bash",
                    "content": "1 passed",
                },
            ],
            "actions": [
                {
                    "action": "edit",
                    "path": "django/utils/dateparse.py",
                    "tool": "str_replace_editor",
                }
            ],
            "patch": (
                "diff --git a/django/utils/dateparse.py b/django/utils/dateparse.py\n"
                "--- a/django/utils/dateparse.py\n"
                "+++ b/django/utils/dateparse.py\n"
                "-old_tz = value\n"
                "+new_tz = normalize(value)"
            ),
            "eval_status": "pass",
            "resolved": True,
            "test_status": "passed",
        },
        {
            "task_id": "sympy__sympy-67890",
            "repo": "sympy/sympy",
            "base_commit": "def456",
            "issue_text": "Improve string printer.",
            "messages": [
                {"role": "user", "content": "Fix printer output."},
                {"role": "assistant", "content": "I edited the printer."},
            ],
            "tool_calls": [
                {
                    "id": "call-2",
                    "name": "python",
                    "args": {"cmd": "pytest sympy/printing/tests/test_str.py"},
                }
            ],
            "actions": [
                {
                    "type": "modify",
                    "file": "sympy/printing/str.py",
                    "tool": "editor",
                }
            ],
            "patch": (
                "diff --git a/sympy/printing/str.py b/sympy/printing/str.py\n"
                "--- a/sympy/printing/str.py\n"
                "+++ b/sympy/printing/str.py\n"
                "+return printer(expr)"
            ),
            "eval_status": "fail",
            "resolved": False,
            "pass": False,
        },
    ]
