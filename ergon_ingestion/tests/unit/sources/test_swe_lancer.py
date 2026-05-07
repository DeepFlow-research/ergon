import csv
import importlib
import json
from pathlib import Path

import pytest

from ergon_ingestion.models import ImportSource


VALID_RESOURCE_KINDS = {"import", "artifact", "report", "output", "search_cache", "note"}


def test_swe_lancer_importer_parses_csv_metadata_only_rows_with_declared_caveats(
    tmp_path: Path,
) -> None:
    swe_lancer = _load_module("ergon_ingestion.sources.swe_lancer")
    source_path = write_swe_lancer_csv_fixture(tmp_path)
    importer = swe_lancer.SweLancerImporter()

    runs = list(
        importer.iter_runs(
            ImportSource(dataset="swe_lancer", input_path=source_path, batch_id="swe-lancer-unit")
        )
    )

    assert [run.source_run_id for run in runs] == [
        "swe-lancer:django__django-001",
        "swe-lancer:sympy__sympy-002",
    ]
    assert [run.instance_key for run in runs] == ["django__django-001", "sympy__sympy-002"]
    assert all(run.schema_fit_class == "metadata-only" for run in runs)
    assert all(run.events == [] for run in runs)

    first = runs[0]
    assert first.observed_fields["repo"] == "django/django"
    assert first.observed_fields["category"] == "bugfix"
    assert first.observed_fields["difficulty"] == "hard"
    assert first.observed_fields["price"] == "320.50"
    assert first.observed_fields["score"] == "0.75"
    assert first.observed_fields["resolved"] == "true"
    assert first.observed_fields["aggregate_metric"] == "0.82"
    assert first.observed_fields["task_prompt"] == "Fix URL resolver regression."

    assert {
        "full_run_trace",
        "patch_artifact",
        "process_actions",
        "evaluator_environment",
    }.issubset(set(first.missing_fields))

    task = one_by_namespace(first.annotations, "swe_lancer.task")
    assert task.payload == {
        "task_id": "django__django-001",
        "instance_id": "django__django-001",
        "repo": "django/django",
        "category": "bugfix",
        "difficulty": "hard",
        "price": 320.5,
    }

    aggregate = one_by_namespace(first.annotations, "swe_lancer.aggregate")
    assert aggregate.payload == {
        "score": 0.75,
        "resolved": True,
        "aggregate_metric": 0.82,
        "rank": 3,
    }

    caveats = one_by_namespace(first.annotations, "swe_lancer.caveats")
    assert caveats.payload["schema_fit_class"] == "metadata-only"
    assert "no_full_run_trace" in caveats.payload["trace"]

    assert [resource.name for resource in first.resources] == [
        "source-record.json",
        "task-prompt.md",
    ]
    assert {resource.kind for resource in first.resources}.issubset(VALID_RESOURCE_KINDS)
    assert first.resources[0].kind == "import"
    assert first.resources[0].payload["task_id"] == "django__django-001"
    assert first.resources[1].kind == "note"
    assert first.resources[1].payload == "Fix URL resolver regression."

    reducers = {reducer.name: reducer for reducer in first.reducers}
    assert set(reducers) == {"swe_lancer.aggregate_metric", "swe_lancer.task_metadata"}
    assert reducers["swe_lancer.aggregate_metric"].fields_read == [
        "task_id",
        "instance_id",
        "repo",
        "score",
        "resolved",
        "aggregate_metric",
        "rank",
    ]
    assert reducers["swe_lancer.aggregate_metric"].output == {
        "task_id": "django__django-001",
        "instance_id": "django__django-001",
        "repo": "django/django",
        "score": 0.75,
        "resolved": True,
        "aggregate_metric": 0.82,
        "rank": 3,
        "convention": "source_reported_metadata_only_aggregate",
    }
    assert reducers["swe_lancer.task_metadata"].fields_read == [
        "task_id",
        "instance_id",
        "repo",
        "category",
        "difficulty",
        "price",
        "task_prompt",
        "problem_statement",
    ]
    assert reducers["swe_lancer.task_metadata"].output == {
        "task_id": "django__django-001",
        "instance_id": "django__django-001",
        "repo": "django/django",
        "category": "bugfix",
        "difficulty": "hard",
        "price": 320.5,
        "has_task_prompt": True,
        "convention": "task_metadata_without_trajectory_or_patch",
    }

    drop_paths = {drop.dropped_field_path for reducer in first.reducers for drop in reducer.drops}
    assert {
        "full_run_trace",
        "patch",
        "process_actions",
        "evaluator_environment",
    }.issubset(drop_paths)


def test_swe_lancer_record_readers_support_json_and_jsonl(tmp_path: Path) -> None:
    swe_lancer = _load_module("ergon_ingestion.sources.swe_lancer")
    records = swe_lancer_records()
    json_path = tmp_path / "swe_lancer.json"
    jsonl_path = tmp_path / "swe_lancer.jsonl"
    json_path.write_text(json.dumps(records))
    jsonl_path.write_text("\n".join(json.dumps(record) for record in records))

    assert list(swe_lancer.iter_swe_lancer_records(json_path)) == records
    assert list(swe_lancer.iter_swe_lancer_records(jsonl_path)) == records


def test_swe_lancer_reducers_preserve_metadata_and_declare_metadata_only_limits() -> None:
    reducers = _load_module("ergon_ingestion.reducers.swe_lancer")
    record = swe_lancer_records()[1]

    aggregate = reducers.aggregate_metric_reducer(record)
    task_metadata = reducers.task_metadata_reducer(record)

    assert aggregate.name == "swe_lancer.aggregate_metric"
    assert aggregate.kind == "original"
    assert aggregate.output == {
        "task_id": "sympy__sympy-002",
        "instance_id": "sympy__sympy-002",
        "repo": "sympy/sympy",
        "score": 0.0,
        "resolved": False,
        "aggregate_metric": 0.2,
        "rank": 19,
        "convention": "source_reported_metadata_only_aggregate",
    }

    assert task_metadata.name == "swe_lancer.task_metadata"
    assert task_metadata.kind == "recovered"
    assert task_metadata.output == {
        "task_id": "sympy__sympy-002",
        "instance_id": "sympy__sympy-002",
        "repo": "sympy/sympy",
        "category": "feature",
        "difficulty": "medium",
        "price": 120.0,
        "has_task_prompt": True,
        "convention": "task_metadata_without_trajectory_or_patch",
    }

    declared = {
        (drop.loss_class, drop.reason, drop.dropped_field_path)
        for drop in aggregate.drops + task_metadata.drops
    }
    assert (
        "unavailable_source_field",
        "swe_lancer_metadata_only_no_full_run_trace",
        "full_run_trace",
    ) in declared
    assert (
        "unavailable_source_field",
        "swe_lancer_metadata_only_no_patch_artifact",
        "patch",
    ) in declared
    assert (
        "unavailable_source_field",
        "swe_lancer_metadata_only_no_process_actions",
        "process_actions",
    ) in declared
    assert (
        "unreproduced_evaluation",
        "swe_lancer_metadata_only_no_evaluator_environment",
        "evaluator_environment",
    ) in declared


def write_swe_lancer_csv_fixture(tmp_path: Path) -> Path:
    source_path = tmp_path / "swe_lancer.csv"
    with source_path.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "task_id",
                "instance_id",
                "repo",
                "category",
                "difficulty",
                "price",
                "score",
                "resolved",
                "aggregate_metric",
                "rank",
                "task_prompt",
                "problem_statement",
            ],
        )
        writer.writeheader()
        writer.writerows(swe_lancer_records())
    return source_path


def swe_lancer_records() -> list[dict]:
    return [
        {
            "task_id": "django__django-001",
            "instance_id": "django__django-001",
            "repo": "django/django",
            "category": "bugfix",
            "difficulty": "hard",
            "price": "320.50",
            "score": "0.75",
            "resolved": "true",
            "aggregate_metric": "0.82",
            "rank": "3",
            "task_prompt": "Fix URL resolver regression.",
            "problem_statement": "",
        },
        {
            "task_id": "",
            "instance_id": "sympy__sympy-002",
            "repo": "sympy/sympy",
            "category": "feature",
            "difficulty": "medium",
            "price": "120",
            "score": "0",
            "resolved": "false",
            "aggregate_metric": "0.20",
            "rank": "19",
            "task_prompt": "",
            "problem_statement": "Add symbolic simplification case.",
        },
    ]


def one_by_namespace(annotations, namespace: str):
    matches = [annotation for annotation in annotations if annotation.namespace == namespace]
    assert len(matches) == 1
    return matches[0]


def _load_module(name: str):
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as exc:
        pytest.fail(f"SWE-Lancer module is not implemented: {exc}")
