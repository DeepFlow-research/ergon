import json
from pathlib import Path

from ergon_ingestion.models import ImportSource
from ergon_ingestion.reducers.swebench_cross_harness import (
    patch_footprint_reducer,
    verdict_reducer,
)
from ergon_ingestion.sources.swebench_cross_harness import SwebenchCrossHarnessImporter


VALID_RESOURCE_KINDS = {"import", "artifact", "report", "output", "search_cache", "note"}


def test_swebench_cross_harness_importer_preserves_artifacts_and_declares_caveats(
    tmp_path: Path,
) -> None:
    source_path = write_cross_harness_jsonl_fixture(tmp_path)
    importer = SwebenchCrossHarnessImporter()

    runs = list(
        importer.iter_runs(
            ImportSource(
                dataset="swebench_cross_harness",
                input_path=source_path,
                batch_id="cross-harness-unit",
            )
        )
    )

    assert [run.source_run_id for run in runs] == [
        "swebench-cross-harness:django__django-12345:modal-v1",
        "cross-run-002",
    ]
    assert [run.instance_key for run in runs] == [
        "django__django-12345",
        "sympy__sympy-67890",
    ]
    assert all(run.schema_fit_class == "artifact-only" for run in runs)
    assert all(run.events == [] for run in runs)
    assert {"agent_trace", "test_environment"}.issubset(runs[0].missing_fields)

    first = runs[0]
    assert first.observed_fields["repo"] == "django/django"
    assert first.observed_fields["base_commit"] == "abc123"
    assert first.observed_fields["harness"] == "modal-v1"
    assert first.observed_fields["harness_version"] == "2026.04"
    assert first.observed_fields["resolved"] is True
    assert first.observed_fields["test_output"] == "2 passed"

    annotations = {annotation.namespace: annotation.payload for annotation in first.annotations}
    assert annotations["swebench_cross_harness.task"] == {
        "instance_id": "django__django-12345",
        "repo": "django/django",
        "base_commit": "abc123",
    }
    assert annotations["swebench_cross_harness.harness"] == {
        "harness": "modal-v1",
        "harness_version": "2026.04",
        "verdict": "resolved",
        "resolved": True,
        "pass": True,
        "fail": False,
    }

    assert [resource.name for resource in first.resources] == [
        "source-record.json",
        "candidate.patch",
        "test-output.txt",
    ]
    assert {resource.kind for resource in first.resources}.issubset(VALID_RESOURCE_KINDS)
    assert first.resources[0].kind == "import"
    assert first.resources[1].kind == "artifact"
    assert first.resources[1].path == tmp_path / "django.patch"
    assert first.resources[1].payload is None
    assert first.resources[2].kind == "report"
    assert first.resources[2].payload == "2 passed"

    second = runs[1]
    assert one_resource_named(second.resources, "candidate.patch").payload == (
        "diff --git a/sympy/core.py b/sympy/core.py\n+fix\n"
    )
    assert one_resource_named(second.resources, "test-log.txt").payload == "failed: assertion"

    reducers = {reducer.name: reducer for reducer in first.reducers}
    assert set(reducers) == {
        "swebench_cross_harness.verdict",
        "swebench_cross_harness.patch_footprint",
    }
    assert reducers["swebench_cross_harness.verdict"].fields_read == [
        "instance_id",
        "repo",
        "base_commit",
        "harness",
        "harness_version",
        "verdict",
        "resolved",
        "pass",
        "fail",
        "test_output",
        "test_log",
    ]
    assert reducers["swebench_cross_harness.verdict"].output == {
        "instance_id": "django__django-12345",
        "repo": "django/django",
        "base_commit": "abc123",
        "harness": "modal-v1",
        "harness_version": "2026.04",
        "verdict": "resolved",
        "resolved": True,
        "pass": True,
        "fail": False,
        "has_test_output": True,
        "has_test_log": False,
        "convention": "source_reported_cross_harness_verdict",
    }
    assert reducers["swebench_cross_harness.patch_footprint"].fields_read == [
        "instance_id",
        "harness",
        "patch",
        "diff",
        "patch_path",
        "test_output",
        "test_log",
    ]
    assert reducers["swebench_cross_harness.patch_footprint"].output == {
        "instance_id": "django__django-12345",
        "harness": "modal-v1",
        "has_patch": True,
        "patch_source": "patch_path",
        "patch_line_count": 5,
        "patch_added_lines": 1,
        "patch_removed_lines": 1,
        "touched_files": ["django/utils/dateparse.py"],
        "has_test_output": True,
        "has_test_log": False,
    }

    declared = {
        (drop.loss_class, drop.reason, drop.dropped_field_path)
        for reducer in first.reducers
        for drop in reducer.drops
    }
    assert (
        "unavailable_source_field",
        "full_agent_trace_absent_from_cross_harness_artifact",
        "agent_trace",
    ) in declared
    assert (
        "unavailable_source_field",
        "test_environment_metadata_absent_from_record",
        "test_environment",
    ) in declared


def test_swebench_cross_harness_reducers_read_verdict_patch_and_conditionally_drop() -> None:
    record = cross_harness_records()[1]

    verdict = verdict_reducer(record)
    footprint = patch_footprint_reducer(record)

    assert verdict.name == "swebench_cross_harness.verdict"
    assert verdict.kind == "original"
    assert verdict.output == {
        "instance_id": "sympy__sympy-67890",
        "repo": "sympy/sympy",
        "base_commit": "def456",
        "harness": "pytest-container",
        "harness_version": "1.9.0",
        "verdict": "failed",
        "resolved": False,
        "pass": False,
        "fail": True,
        "has_test_output": False,
        "has_test_log": True,
        "convention": "source_reported_cross_harness_verdict",
    }

    assert footprint.name == "swebench_cross_harness.patch_footprint"
    assert footprint.kind == "recovered"
    assert footprint.output == {
        "instance_id": "sympy__sympy-67890",
        "harness": "pytest-container",
        "has_patch": True,
        "patch_source": "patch",
        "patch_line_count": 2,
        "patch_added_lines": 1,
        "patch_removed_lines": 0,
        "touched_files": ["sympy/core.py"],
        "has_test_output": False,
        "has_test_log": True,
    }

    declared_drops = {
        (drop.reason, drop.dropped_field_path)
        for reducer in [verdict, footprint]
        for drop in reducer.drops
    }
    assert (
        "full_agent_trace_absent_from_cross_harness_artifact",
        "agent_trace",
    ) in declared_drops
    assert (
        "test_environment_metadata_absent_from_record",
        "test_environment",
    ) in declared_drops


def write_cross_harness_jsonl_fixture(tmp_path: Path) -> Path:
    patch_path = tmp_path / "django.patch"
    patch_path.write_text(
        "diff --git a/django/utils/dateparse.py b/django/utils/dateparse.py\n"
        "--- a/django/utils/dateparse.py\n"
        "+++ b/django/utils/dateparse.py\n"
        "-old_tz = value\n"
        "+new_tz = normalize(value)\n"
    )
    records = cross_harness_records(patch_path=patch_path)
    source_path = tmp_path / "swebench_cross_harness.jsonl"
    source_path.write_text("\n".join(json.dumps(record) for record in records))
    return source_path


def cross_harness_records(patch_path: Path | None = None) -> list[dict]:
    return [
        {
            "instance_id": "django__django-12345",
            "repo": "django/django",
            "base_commit": "abc123",
            "harness": "modal-v1",
            "harness_version": "2026.04",
            "patch_path": str(patch_path or "django.patch"),
            "verdict": "resolved",
            "resolved": True,
            "pass": True,
            "fail": False,
            "test_output": "2 passed",
        },
        {
            "source_run_id": "cross-run-002",
            "instance_id": "sympy__sympy-67890",
            "repo": "sympy/sympy",
            "base_commit": "def456",
            "harness": "pytest-container",
            "harness_version": "1.9.0",
            "patch": "diff --git a/sympy/core.py b/sympy/core.py\n+fix\n",
            "verdict": "failed",
            "resolved": False,
            "pass": False,
            "fail": True,
            "test_log": "failed: assertion",
        },
    ]


def one_resource_named(resources, name: str):
    matches = [resource for resource in resources if resource.name == name]
    assert len(matches) == 1
    return matches[0]
