import csv
import importlib
import json
from pathlib import Path

import pytest

from ergon_ingestion.models import ImportSource


VALID_RESOURCE_KINDS = {"import", "artifact", "report", "output", "search_cache", "note"}


def test_swe_smith_importer_parses_jsonl_patch_rows_with_declared_trace_caveats(
    tmp_path: Path,
) -> None:
    swe_smith = _load_module("ergon_ingestion.sources.swe_smith")
    source_path = write_swe_smith_jsonl_fixture(tmp_path)
    importer = swe_smith.SweSmithImporter()

    runs = list(
        importer.iter_runs(
            ImportSource(dataset="swe_smith", input_path=source_path, batch_id="swe-smith-unit")
        )
    )

    assert [run.source_run_id for run in runs] == ["swe-smith:django__django-001", "run-002"]
    assert [run.instance_key for run in runs] == ["django__django-001", "sympy__sympy-002"]
    assert all(run.schema_fit_class == "full-trace" for run in runs)
    assert all(run.events == [] for run in runs)

    first = runs[0]
    assert first.observed_fields["repo"] == "django/django"
    assert first.observed_fields["base_commit"] == "abc123"
    assert first.observed_fields["problem_statement"] == "Fix URL resolver regression."
    assert first.observed_fields["patch"] == "diff --git a/django/urls.py b/django/urls.py\n+fix\n"
    assert first.observed_fields["eval_status"] == "resolved"
    assert first.observed_fields["resolved"] is True
    assert first.observed_fields["generator"]["model"] == "smith-generator-v1"

    assert {
        "interaction_trace",
        "evaluator_reproduction",
        "test_execution_log",
    }.issubset(set(first.missing_fields))

    assert [resource.name for resource in first.resources] == [
        "source-record.json",
        "candidate.patch",
        "issue.md",
    ]
    assert {resource.kind for resource in first.resources}.issubset(VALID_RESOURCE_KINDS)
    assert first.resources[0].kind == "import"
    assert first.resources[1].kind == "artifact"
    assert first.resources[1].mime_type == "text/x-diff"
    assert first.resources[1].payload == "diff --git a/django/urls.py b/django/urls.py\n+fix\n"
    assert first.resources[2].kind == "note"
    assert first.resources[2].payload == "Fix URL resolver regression."

    reducers = {reducer.name: reducer for reducer in first.reducers}
    assert set(reducers) == {"swe_smith.resolved", "swe_smith.patch_record"}
    assert reducers["swe_smith.resolved"].fields_read == [
        "instance_id",
        "task_id",
        "eval_status",
        "resolved",
        "evaluation.resolved",
        "evaluation.status",
    ]
    assert reducers["swe_smith.resolved"].output == {
        "instance_id": "django__django-001",
        "resolved": True,
        "eval_status": "resolved",
        "convention": "source_reported_outcome",
    }
    assert reducers["swe_smith.patch_record"].fields_read == [
        "instance_id",
        "task_id",
        "repo",
        "base_commit",
        "patch",
        "diff",
        "generator",
        "generator_metadata",
    ]
    assert reducers["swe_smith.patch_record"].output == {
        "instance_id": "django__django-001",
        "repo": "django/django",
        "base_commit": "abc123",
        "has_patch": True,
        "patch_bytes": len("diff --git a/django/urls.py b/django/urls.py\n+fix\n".encode()),
        "generator": {"model": "smith-generator-v1", "temperature": 0.2},
        "convention": "patch_row_record",
    }

    drop_reasons = {drop.reason for reducer in first.reducers for drop in reducer.drops}
    assert "full_interaction_trace_absent_from_patch_row" in drop_reasons
    assert "trusts_source_eval_status_without_reproducing_evaluator" in drop_reasons


def test_swe_smith_importer_parses_csv_rows_with_patch_and_nested_outcome(
    tmp_path: Path,
) -> None:
    swe_smith = _load_module("ergon_ingestion.sources.swe_smith")
    source_path = write_swe_smith_csv_fixture(tmp_path)
    importer = swe_smith.SweSmithImporter()

    runs = list(
        importer.iter_runs(
            ImportSource(dataset="swe_smith", input_path=source_path, batch_id="swe-smith-csv-unit")
        )
    )

    assert len(runs) == 1
    run = runs[0]
    assert run.source_run_id == "swe-smith:pallets__flask-003"
    assert run.instance_key == "pallets__flask-003"
    assert run.schema_fit_class == "full-trace"
    assert run.events == []
    assert run.observed_fields["resolved"] == "false"
    assert (
        one_resource_named(run.resources, "candidate.patch").payload
        == "diff --git a/app.py b/app.py\n-fail\n"
    )

    reducers = {reducer.name: reducer for reducer in run.reducers}
    assert reducers["swe_smith.resolved"].output == {
        "instance_id": "pallets__flask-003",
        "resolved": False,
        "eval_status": "failed",
        "convention": "source_reported_outcome",
    }
    assert reducers["swe_smith.patch_record"].output["patch_bytes"] == len(
        "diff --git a/app.py b/app.py\n-fail\n".encode()
    )


def test_swe_smith_reducers_read_outcome_patch_metadata_and_declare_limits() -> None:
    reducers = _load_module("ergon_ingestion.reducers.swe_smith")
    record = swe_smith_records()[1]

    resolved = reducers.resolved_reducer(record)
    patch_record = reducers.patch_record_reducer(record)

    assert resolved.name == "swe_smith.resolved"
    assert resolved.kind == "original"
    assert resolved.output == {
        "instance_id": "sympy__sympy-002",
        "resolved": False,
        "eval_status": "failed",
        "convention": "source_reported_outcome",
    }

    assert patch_record.name == "swe_smith.patch_record"
    assert patch_record.kind == "recovered"
    assert patch_record.output == {
        "instance_id": "sympy__sympy-002",
        "repo": "sympy/sympy",
        "base_commit": "def456",
        "has_patch": True,
        "patch_bytes": len("diff --git a/sympy/core.py b/sympy/core.py\n-nope\n".encode()),
        "generator": {"seed": 17},
        "convention": "patch_row_record",
    }

    declared = {
        (drop.loss_class, drop.reason, drop.dropped_field_path)
        for drop in resolved.drops + patch_record.drops
    }
    assert (
        "unavailable_source_field",
        "full_interaction_trace_absent_from_patch_row",
        "interaction_trace",
    ) in declared
    assert (
        "unreproduced_evaluation",
        "trusts_source_eval_status_without_reproducing_evaluator",
        "evaluation",
    ) in declared


def write_swe_smith_jsonl_fixture(tmp_path: Path) -> Path:
    source_path = tmp_path / "swe_smith.jsonl"
    source_path.write_text("\n".join(json.dumps(record) for record in swe_smith_records()))
    return source_path


def write_swe_smith_csv_fixture(tmp_path: Path) -> Path:
    source_path = tmp_path / "swe_smith.csv"
    with source_path.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "instance_id",
                "repo",
                "base_commit",
                "issue",
                "diff",
                "eval_status",
                "resolved",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "instance_id": "pallets__flask-003",
                "repo": "pallets/flask",
                "base_commit": "fed789",
                "issue": "Repair request context leak.",
                "diff": "diff --git a/app.py b/app.py\n-fail\n",
                "eval_status": "failed",
                "resolved": "false",
            }
        )
    return source_path


def swe_smith_records() -> list[dict]:
    return [
        {
            "instance_id": "django__django-001",
            "repo": "django/django",
            "base_commit": "abc123",
            "problem_statement": "Fix URL resolver regression.",
            "patch": "diff --git a/django/urls.py b/django/urls.py\n+fix\n",
            "eval_status": "resolved",
            "resolved": True,
            "generator": {"model": "smith-generator-v1", "temperature": 0.2},
        },
        {
            "task_id": "sympy__sympy-002",
            "source_run_id": "run-002",
            "repo": "sympy/sympy",
            "base_commit": "def456",
            "issue": "Simplify rational expression failure.",
            "diff": "diff --git a/sympy/core.py b/sympy/core.py\n-nope\n",
            "evaluation": {"status": "failed", "resolved": False},
            "generator_metadata": {"seed": 17},
        },
    ]


def one_resource_named(resources, name: str):
    matches = [resource for resource in resources if resource.name == name]
    assert len(matches) == 1
    return matches[0]


def _load_module(name: str):
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as exc:
        pytest.fail(f"SWE-smith module is not implemented: {exc}")
