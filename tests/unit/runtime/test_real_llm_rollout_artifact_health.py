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
    resource_rows: list[dict] | None = None,
    task_execution_ids: list[str] | None = None,
) -> None:
    execution_ids = task_execution_ids or [str(uuid4()) for _ in range(task_count)]
    resources = resource_rows
    if resources is None:
        resources = [
            {
                "id": str(uuid4()),
                "task_execution_id": execution_ids[0],
                "kind": "report",
                "name": "report.md",
                "file_path": "/durable/blob",
            }
        ]
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
                    "run_resources": len(resources),
                    "run_graph_nodes": task_count,
                },
            }
        )
    )
    _write_jsonl(
        db / "run_task_executions.jsonl",
        [
            {
                "id": execution_ids[idx],
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
    _write_jsonl(db / "run_resources.jsonl", resources)
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


def test_artifact_health_uses_task_scoped_report_resources(tmp_path: Path) -> None:
    task_execution_id = str(uuid4())
    _write_minimal_rollout(
        tmp_path,
        task_count=1,
        evaluation_rows=[
            {
                "id": str(uuid4()),
                "task_execution_id": task_execution_id,
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
        resource_rows=[
            {
                "id": str(uuid4()),
                "task_execution_id": task_execution_id,
                "kind": "report",
                "name": "report.md",
                "file_path": "/durable/blob/not/final_output",
                "metadata_json": {"sandbox_origin": "/workspace/final_output/report.md"},
            }
        ],
        task_execution_ids=[task_execution_id],
    )

    health = analyze_rollout_artifacts(tmp_path, expected_task_count=1)

    assert health.missing_final_report is False
    assert not any(issue.code == "missing_final_report" for issue in health.issues)


def test_artifact_health_flags_completed_task_without_report_resource(tmp_path: Path) -> None:
    task_execution_id = str(uuid4())
    _write_minimal_rollout(
        tmp_path,
        task_count=1,
        evaluation_rows=[
            {
                "id": str(uuid4()),
                "task_execution_id": task_execution_id,
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
        resource_rows=[
            {
                "id": str(uuid4()),
                "task_execution_id": task_execution_id,
                "kind": "note",
                "name": "notes.md",
                "file_path": "/durable/blob",
            }
        ],
        task_execution_ids=[task_execution_id],
    )

    health = analyze_rollout_artifacts(tmp_path, expected_task_count=1)

    assert health.ok is False
    assert health.missing_final_report is True
    assert any(issue.code == "missing_final_report" for issue in health.issues)


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
