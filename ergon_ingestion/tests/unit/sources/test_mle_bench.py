import importlib
import json
from pathlib import Path

import pytest

from ergon_ingestion.models import ImportSource


VALID_RESOURCE_KINDS = {"import", "artifact", "report", "output", "search_cache", "note"}


def test_mle_bench_importer_emits_artifact_only_runs_with_archived_files(
    tmp_path: Path,
) -> None:
    mle_bench = _load_module("ergon_ingestion.sources.mle_bench")
    source_path = write_mle_bench_fixture(tmp_path)
    importer = mle_bench.MleBenchImporter()

    runs = list(
        importer.iter_runs(
            ImportSource(dataset="mle_bench", input_path=source_path, batch_id="mle-unit")
        )
    )

    assert [run.source_run_id for run in runs] == ["mle:feedback-prize:sub-001", "mle:otto:sub-002"]
    assert [run.instance_key for run in runs] == ["feedback-prize:sub-001", "otto:sub-002"]
    assert all(run.schema_fit_class == "artifact-only" for run in runs)
    assert all(run.events == [] for run in runs)

    first = runs[0]
    assert first.observed_fields["submission_id"] == "sub-001"
    assert first.observed_fields["competition_id"] == "feedback-prize"
    assert first.observed_fields["score"] == 0.8421
    assert first.observed_fields["medal"] == "gold"
    assert first.observed_fields["medal_thresholds"] == {
        "gold": 0.84,
        "silver": 0.82,
        "bronze": 0.8,
    }
    assert {
        "live_reexecution_environment",
        "competition_private_test_runtime",
        "container_image",
    }.issubset(set(first.missing_fields))

    assert [resource.name for resource in first.resources] == [
        "source-record.json",
        "notebook.ipynb",
        "submission.csv",
    ]
    assert {resource.kind for resource in first.resources}.issubset(VALID_RESOURCE_KINDS)
    assert first.resources[0].kind == "import"
    assert first.resources[1].kind == "artifact"
    assert first.resources[1].path == Path("submissions/sub-001/notebook.ipynb")
    assert first.resources[1].payload == {"cells": [{"cell_type": "code", "source": "train()"}]}
    assert first.resources[2].kind == "output"
    assert first.resources[2].payload == "id,target\n1,0.7\n"

    reducers = {reducer.name: reducer for reducer in first.reducers}
    assert set(reducers) == {"mle_bench.score", "mle_bench.medal_threshold"}
    assert reducers["mle_bench.score"].fields_read == [
        "submission_id",
        "competition_id",
        "score",
        "score_direction",
    ]
    assert reducers["mle_bench.score"].output == {
        "submission_id": "sub-001",
        "competition_id": "feedback-prize",
        "score": 0.8421,
        "score_direction": "higher_is_better",
        "convention": "archived_artifact_score",
    }
    assert reducers["mle_bench.medal_threshold"].fields_read == [
        "medal",
        "medal_thresholds",
        "score",
    ]
    assert reducers["mle_bench.medal_threshold"].output == {
        "medal": "gold",
        "thresholds": {"gold": 0.84, "silver": 0.82, "bronze": 0.8},
        "score": 0.8421,
        "convention": "archived_leaderboard_thresholds",
    }

    drop_paths = {
        drop.dropped_field_path
        for reducer in first.reducers
        for drop in reducer.drops
    }
    drop_reasons = {drop.reason for reducer in first.reducers for drop in reducer.drops}
    assert "live_reexecution_environment" in drop_paths
    assert "competition_private_test_runtime" in drop_paths
    assert "live_execution_env_unavailable_for_archived_artifact" in drop_reasons


def test_mle_bench_reducers_preserve_score_medal_and_declared_artifact_limits() -> None:
    reducers = _load_module("ergon_ingestion.reducers.mle_bench")
    record = mle_bench_records()[1]

    score = reducers.score_reducer(record)
    medal = reducers.medal_threshold_reducer(record)

    assert score.name == "mle_bench.score"
    assert score.kind == "original"
    assert score.fields_read == ["submission_id", "competition_id", "score", "score_direction"]
    assert score.output == {
        "submission_id": "sub-002",
        "competition_id": "otto",
        "score": 0.771,
        "score_direction": "lower_is_better",
        "convention": "archived_artifact_score",
    }

    assert medal.name == "mle_bench.medal_threshold"
    assert medal.kind == "recovered"
    assert medal.fields_read == ["medal", "medal_thresholds", "score"]
    assert medal.output == {
        "medal": "bronze",
        "thresholds": {"gold": 0.75, "silver": 0.765, "bronze": 0.78},
        "score": 0.771,
        "convention": "archived_leaderboard_thresholds",
    }

    drops = score.drops + medal.drops
    assert {
        (drop.loss_class, drop.reason, drop.dropped_field_path)
        for drop in drops
    } >= {
        (
            "unavailable_source_field",
            "live_execution_env_unavailable_for_archived_artifact",
            "live_reexecution_environment",
        ),
        (
            "unavailable_source_field",
            "live_execution_env_unavailable_for_archived_artifact",
            "competition_private_test_runtime",
        ),
    }


def write_mle_bench_fixture(tmp_path: Path) -> Path:
    source_path = tmp_path / "mle_bench.jsonl"
    source_path.write_text("\n".join(json.dumps(record) for record in mle_bench_records()))
    return source_path


def mle_bench_records() -> list[dict]:
    return [
        {
            "submission_id": "sub-001",
            "competition_id": "feedback-prize",
            "score": 0.8421,
            "score_direction": "higher_is_better",
            "medal": "gold",
            "medal_thresholds": {"gold": 0.84, "silver": 0.82, "bronze": 0.8},
            "artifacts": [
                {
                    "path": "submissions/sub-001/notebook.ipynb",
                    "kind": "artifact",
                    "mime_type": "application/x-ipynb+json",
                    "payload": {"cells": [{"cell_type": "code", "source": "train()"}]},
                },
                {
                    "path": "submissions/sub-001/submission.csv",
                    "kind": "output",
                    "mime_type": "text/csv",
                    "payload": "id,target\n1,0.7\n",
                },
            ],
        },
        {
            "submission_id": "sub-002",
            "competition_id": "otto",
            "score": 0.771,
            "score_direction": "lower_is_better",
            "medal": "bronze",
            "medal_thresholds": {"gold": 0.75, "silver": 0.765, "bronze": 0.78},
            "artifacts": [
                {
                    "path": "submissions/sub-002/notebook.ipynb",
                    "kind": "artifact",
                    "mime_type": "application/x-ipynb+json",
                    "payload": {"cells": [{"cell_type": "markdown", "source": "feature notes"}]},
                }
            ],
        },
    ]


def _load_module(name: str):
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as exc:
        pytest.fail(f"MLE-Bench module is not implemented: {exc}")
