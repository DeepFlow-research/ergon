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
    workflow_tool_calls: int = 0
    other_tool_calls: int = 0
    budget_exhausted: bool = False
    missing_final_report: bool = False
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


def _payload(row: dict[str, Any]) -> dict[str, Any]:  # slopcop: ignore[no-typing-any]
    payload = row.get("payload") or {}
    if isinstance(payload, str):
        return json.loads(payload)
    return payload if isinstance(payload, dict) else {}


def _contains_budget_exhaustion(value: Any) -> bool:  # slopcop: ignore[no-typing-any]
    if isinstance(value, dict):
        if value.get("status") == "TOOL_BUDGET_EXHAUSTED":
            return True
        return any(_contains_budget_exhaustion(v) for v in value.values())
    if isinstance(value, list):
        return any(_contains_budget_exhaustion(v) for v in value)
    return False


def _tool_budget_signals(
    context_events: list[dict[str, Any]],  # slopcop: ignore[no-typing-any]
) -> tuple[int, int, bool]:
    workflow_tool_calls = 0
    other_tool_calls = 0
    budget_exhausted = False
    for event in context_events:
        payload = _payload(event)
        budget_exhausted = budget_exhausted or _contains_budget_exhaustion(payload)
        if event.get("event_type") != "tool_call":
            continue
        tool_name = payload.get("tool_name")
        if tool_name == "workflow":
            workflow_tool_calls += 1
        elif tool_name:
            other_tool_calls += 1
    return workflow_tool_calls, other_tool_calls, budget_exhausted


def _is_completed_execution(row: dict[str, Any]) -> bool:  # slopcop: ignore[no-typing-any]
    return row.get("status") == "completed"


def _is_report_resource(row: dict[str, Any]) -> bool:  # slopcop: ignore[no-typing-any]
    return row.get("kind") == "report"


def _missing_task_report(
    executions: list[dict[str, Any]],  # slopcop: ignore[no-typing-any]
    resources: list[dict[str, Any]],  # slopcop: ignore[no-typing-any]
) -> bool:
    completed_execution_ids = {
        str(row["id"])
        for row in executions
        if row.get("id") is not None and _is_completed_execution(row)
    }
    if not completed_execution_ids:
        return False

    report_execution_ids = {
        str(resource["task_execution_id"])
        for resource in resources
        if resource.get("task_execution_id") is not None and _is_report_resource(resource)
    }
    return not completed_execution_ids.issubset(report_execution_ids)


def analyze_rollout_artifacts(  # noqa: C901
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
    context_events = _read_jsonl(db_dir / "run_context_events.jsonl")

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
    workflow_tool_calls, other_tool_calls, budget_exhausted = _tool_budget_signals(
        context_events,
    )
    missing_final_report = _missing_task_report(executions, resources)

    issues: list[ArtifactHealthIssue] = []
    if expected_task_count is not None and task_count != expected_task_count:
        issues.append(
            ArtifactHealthIssue(
                code="task_count_mismatch",
                message=f"Expected {expected_task_count} task executions, found {task_count}.",
            )
        )
    if expected_evaluation_count is not None and evaluation_count < expected_evaluation_count:
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
    if missing_final_report:
        issues.append(
            ArtifactHealthIssue(
                code="missing_final_report",
                message="A completed task execution has no task-scoped report resource.",
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
        workflow_tool_calls=workflow_tool_calls,
        other_tool_calls=other_tool_calls,
        budget_exhausted=budget_exhausted,
        missing_final_report=missing_final_report,
        normalized_scores=normalized_scores,
        worker_slugs=worker_slugs,
        issues=issues,
    )
