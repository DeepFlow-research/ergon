"""Pure artifact health checks for real-LLM rollout directories."""

import json
from pathlib import Path
from typing import Any  # slopcop: ignore[no-typing-any]

from pydantic import BaseModel, Field


class ArtifactHealthIssue(BaseModel):
    """One machine-readable health issue found in a rollout artifact directory."""

    code: str
    message: str

    model_config = {"frozen": True}


class ArtifactHealthSummary(BaseModel):
    """Rollout health summary derived from dumped files only."""

    ok: bool
    task_count: int
    evaluation_count: int
    resource_count: int
    graph_node_count: int
    criterion_count: int
    normalized_scores: list[float] = Field(default_factory=list)
    worker_slugs: list[str] = Field(default_factory=list)
    issues: list[ArtifactHealthIssue] = Field(default_factory=list)

    model_config = {"frozen": True}


def _read_json(path: Path) -> dict[str, Any]:  # slopcop: ignore[no-typing-any]
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def _read_jsonl(path: Path) -> list[dict[str, Any]]:  # slopcop: ignore[no-typing-any]
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _summary_json(row: dict[str, Any]) -> dict[str, Any]:  # slopcop: ignore[no-typing-any]
    summary = row.get("summary_json") or {}
    if isinstance(summary, str):
        return json.loads(summary)
    return summary


def _criterion_has_reasoning(criterion: dict[str, Any]) -> bool:  # slopcop: ignore[no-typing-any]
    return bool(criterion.get("feedback") or criterion.get("model_reasoning"))


def analyze_rollout_artifacts(
    out_dir: Path,
    *,
    expected_task_count: int | None = None,
    expected_evaluation_count: int | None = None,
    require_screenshots: bool = False,
) -> ArtifactHealthSummary:
    """Analyze a rollout directory without importing DB/runtime models."""
    manifest = _read_json(out_dir / "manifest.json")
    db_dir = out_dir / "db"
    executions = _read_jsonl(db_dir / "run_task_executions.jsonl")
    evaluations = _read_jsonl(db_dir / "run_task_evaluations.jsonl")
    resources = _read_jsonl(db_dir / "run_resources.jsonl")
    graph_nodes = _read_jsonl(db_dir / "run_graph_nodes.jsonl")

    task_count = len(executions)
    evaluation_count = len(evaluations)
    resource_count = len(resources)
    graph_node_count = len(graph_nodes)
    worker_slugs = sorted(
        {
            slug
            for node in graph_nodes
            if (slug := node.get("assigned_worker_slug") or node.get("assignedWorkerSlug"))
        }
    )

    issues: list[ArtifactHealthIssue] = []
    if expected_task_count is not None and task_count != expected_task_count:
        issues.append(
            ArtifactHealthIssue(
                code="task_count_mismatch",
                message=f"Expected {expected_task_count} task executions, found {task_count}.",
            )
        )
    if (
        expected_evaluation_count is not None
        and evaluation_count < expected_evaluation_count
    ):
        issues.append(
            ArtifactHealthIssue(
                code="missing_evaluations",
                message=(
                    f"Expected at least {expected_evaluation_count} evaluation rows, "
                    f"found {evaluation_count}."
                ),
            )
        )
    if resource_count == 0:
        issues.append(
            ArtifactHealthIssue(
                code="missing_resources",
                message="No resources were dumped for a completed rollout.",
            )
        )
    if expected_task_count is not None and graph_node_count < expected_task_count:
        issues.append(
            ArtifactHealthIssue(
                code="missing_graph_nodes",
                message=(
                    f"Expected at least {expected_task_count} graph nodes, "
                    f"found {graph_node_count}."
                ),
            )
        )

    normalized_scores: list[float] = []
    criterion_count = 0
    for row_idx, evaluation in enumerate(evaluations):
        summary = _summary_json(evaluation)
        normalized = summary.get("normalized_score", evaluation.get("score"))
        if isinstance(normalized, int | float):
            normalized_scores.append(float(normalized))

        criteria = summary.get("criterion_results") or []
        criterion_count += len(criteria)
        if not criteria:
            issues.append(
                ArtifactHealthIssue(
                    code="criteria_missing",
                    message=f"Evaluation row {row_idx} has no criterion_results.",
                )
            )
        for criterion_idx, criterion in enumerate(criteria):
            if not _criterion_has_reasoning(criterion):
                issues.append(
                    ArtifactHealthIssue(
                        code="criterion_reasoning_missing",
                        message=(
                            f"Evaluation row {row_idx} criterion {criterion_idx} has no "
                            "feedback or model_reasoning."
                        ),
                    )
                )

    if require_screenshots and not (manifest.get("screenshots") or {}):
        issues.append(
            ArtifactHealthIssue(
                code="screenshots_missing",
                message="Dashboard screenshots were requested but none were captured.",
            )
        )

    return ArtifactHealthSummary(
        ok=not issues,
        task_count=task_count,
        evaluation_count=evaluation_count,
        resource_count=resource_count,
        graph_node_count=graph_node_count,
        criterion_count=criterion_count,
        normalized_scores=normalized_scores,
        worker_slugs=worker_slugs,
        issues=issues,
    )
