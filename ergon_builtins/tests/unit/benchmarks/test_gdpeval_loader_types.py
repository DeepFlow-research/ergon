from pathlib import Path

from ergon_builtins.benchmarks.gdpeval.loader import load_rubric_data, load_single_rubric
from ergon_builtins.benchmarks.gdpeval.task_schemas import GDPRubricData


def test_load_rubric_data_returns_typed_rubric_records(
    tmp_path: Path,
    monkeypatch,
) -> None:
    rubric_file = tmp_path / "rubrics.jsonl"
    rubric_file.write_text(
        '{"task_id": "task-1", "category_name": "docs", '
        '"max_total_score": 1.0, "stages": [], "rationale": "fixture"}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "ergon_builtins.benchmarks.gdpeval.loader.hf_hub_download",
        lambda **_: str(rubric_file),
    )

    rubrics = load_rubric_data()

    assert isinstance(rubrics["task-1"], GDPRubricData)
    assert rubrics["task-1"].task_id == "task-1"
    assert rubrics["task-1"].category_name == "docs"


def test_loader_normalizes_hf_max_score_to_score_spec(
    tmp_path: Path,
    monkeypatch,
) -> None:
    rubric_file = tmp_path / "rubrics.jsonl"
    rubric_file.write_text(
        '{"task_id": "task-1", "category_name": "docs", '
        '"max_total_score": 1.0, "stages": [{"name": "stage", '
        '"max_points": 2.0, "criteria": [{"name": "criterion", '
        '"code_template": "True", "max_score": 2.0}]}]}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "ergon_builtins.benchmarks.gdpeval.loader.hf_hub_download",
        lambda **_: str(rubric_file),
    )

    rubric = load_single_rubric("task-1")

    criterion = rubric.stages[0].criteria[0]
    assert criterion.score_spec.max_score == 2.0
    assert "max_score" not in criterion.model_dump()


def test_load_single_rubric_returns_typed_record(
    tmp_path: Path,
    monkeypatch,
) -> None:
    rubric_file = tmp_path / "rubrics.jsonl"
    rubric_file.write_text(
        '{"task_id": "task-1", "category_name": "docs", "max_total_score": 1.0, "stages": []}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "ergon_builtins.benchmarks.gdpeval.loader.hf_hub_download",
        lambda **_: str(rubric_file),
    )

    rubric = load_single_rubric("task-1")

    assert isinstance(rubric, GDPRubricData)
    assert rubric.task_id == "task-1"
