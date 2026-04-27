"""Artifact health contracts for real-LLM rollout dumps."""

import json
from pathlib import Path
from uuid import uuid4

from tests.real_llm.artifact_health import analyze_rollout_artifacts
from tests.real_llm.rollout import write_report


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(f"{json.dumps(row)}\n" for row in rows))


def _write_minimal_rollout(
    root: Path,
    *,
    task_count: int = 1,
    evaluation_rows: list[dict] | None = None,
    resource_count: int = 1,
) -> None:
    db = root / "db"
    db.mkdir()
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "run_id": str(uuid4()),
                "benchmark": "researchrubrics",
                "worker": "researchrubrics-researcher",
                "evaluator": "research-rubric",
                "model": "stub:constant",
                "cli_returncode": 0,
                "terminal_status": "completed",
                "wall_clock": {"duration_seconds": 1.0},
                "screenshots": {},
                "db_row_counts": {
                    "run_task_executions": task_count,
                    "run_task_evaluations": len(evaluation_rows or []),
                    "run_resources": resource_count,
                    "run_graph_nodes": task_count,
                },
            }
        )
    )
    _write_jsonl(
        db / "run_task_executions.jsonl",
        [
            {
                "id": str(uuid4()),
                "task_slug": f"task-{idx}",
                "status": "completed",
            }
            for idx in range(task_count)
        ],
    )
    _write_jsonl(
        db / "run_graph_nodes.jsonl",
        [
            {
                "id": str(uuid4()),
                "task_slug": f"task-{idx}",
                "status": "completed",
                "assigned_worker_slug": "researchrubrics-researcher",
                "level": 0,
            }
            for idx in range(task_count)
        ],
    )
    _write_jsonl(db / "run_resources.jsonl", [{"id": str(uuid4())} for _ in range(resource_count)])
    _write_jsonl(db / "run_task_evaluations.jsonl", evaluation_rows or [])


def test_artifact_health_fails_when_completed_tasks_lack_evaluations(tmp_path: Path) -> None:
    _write_minimal_rollout(tmp_path, task_count=2, evaluation_rows=[])

    health = analyze_rollout_artifacts(tmp_path, expected_task_count=2, expected_evaluation_count=2)

    assert health.ok is False
    assert any(issue.code == "missing_evaluations" for issue in health.issues)


def test_artifact_health_requires_criterion_reasoning(tmp_path: Path) -> None:
    _write_minimal_rollout(
        tmp_path,
        evaluation_rows=[
            {
                "id": str(uuid4()),
                "summary_json": {
                    "evaluator_name": "research-rubric",
                    "criterion_results": [
                        {
                            "criterion_name": "criterion_0",
                            "criterion_type": "researchrubrics-llm-judge",
                            "score": 1.0,
                            "max_score": 1.0,
                            "passed": True,
                            "weight": 1.0,
                            "status": "passed",
                            "criterion_description": "Includes citations.",
                            "feedback": None,
                            "model_reasoning": None,
                        }
                    ],
                },
            }
        ],
    )

    health = analyze_rollout_artifacts(tmp_path, expected_task_count=1)

    assert health.ok is False
    assert any(issue.code == "criterion_reasoning_missing" for issue in health.issues)


def test_artifact_health_summarizes_scores_and_workers(tmp_path: Path) -> None:
    _write_minimal_rollout(
        tmp_path,
        evaluation_rows=[
            {
                "id": str(uuid4()),
                "score": 0.75,
                "summary_json": {
                    "evaluator_name": "research-rubric",
                    "normalized_score": 0.75,
                    "criterion_results": [
                        {
                            "criterion_name": "criterion_0",
                            "criterion_type": "researchrubrics-llm-judge",
                            "score": 1.0,
                            "max_score": 1.0,
                            "passed": True,
                            "weight": 1.0,
                            "status": "passed",
                            "criterion_description": "Includes citations.",
                            "feedback": "The report cited source material.",
                            "model_reasoning": "The report cited source material.",
                        }
                    ],
                },
            }
        ],
    )

    health = analyze_rollout_artifacts(tmp_path, expected_task_count=1)

    assert health.ok is True
    assert health.task_count == 1
    assert health.evaluation_count == 1
    assert health.criterion_count == 1
    assert health.normalized_scores == [0.75]
    assert health.worker_slugs == ["researchrubrics-researcher"]


def test_rollout_report_includes_artifact_health_section(tmp_path: Path) -> None:
    _write_minimal_rollout(
        tmp_path,
        evaluation_rows=[
            {
                "id": str(uuid4()),
                "score": 0.75,
                "summary_json": {
                    "evaluator_name": "research-rubric",
                    "normalized_score": 0.75,
                    "criterion_results": [
                        {
                            "criterion_name": "criterion_0",
                            "criterion_type": "researchrubrics-llm-judge",
                            "score": 1.0,
                            "max_score": 1.0,
                            "passed": True,
                            "weight": 1.0,
                            "status": "passed",
                            "criterion_description": "Includes citations.",
                            "feedback": "The report cited source material.",
                        }
                    ],
                },
            }
        ],
    )

    report_path = write_report(tmp_path, tmp_path / "manifest.json")

    report = report_path.read_text()
    assert "## Artifact health" in report
    assert "- status: **ok**" in report
    assert "- normalized scores: 0.750" in report
    assert "- worker slugs: `researchrubrics-researcher`" in report
