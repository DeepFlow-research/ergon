# Adapted from pinned MAG source; see NOTICE and source-manifest.json.
"""
Standard evaluation rules and regret category configuration for all demos.

Adds strict punishments for poor workflow outcomes:
- End deliverable quality (LLM)
- Completion ratio and must-complete checks
- Runtime efficiency vs plan
- Cost efficiency vs plan

Utilities to merge these standard categories into demo-specific category configs.
"""

from __future__ import annotations
import math
from ergon_builtins.benchmarks.manager_gym.source_types import Workflow
from ergon_builtins.benchmarks.manager_gym.source_types import ValidationContext
from ergon_builtins.benchmarks.manager_gym.source_types import TaskStatus


def speed_rubric(workflow: Workflow) -> tuple[float, str]:
    expected = sum((float(t.estimated_duration_hours or 0.0) for t in workflow.tasks.values()))
    actual = (
        (workflow.completed_at - workflow.started_at).total_seconds() / 3600.0
        if workflow.started_at and workflow.completed_at
        else 0.0
    )
    expected = max(expected, 1e-06)
    actual = max(actual, 1e-06)
    log_ratio = math.log(expected / actual)
    normalized = 1.0 / (1.0 + math.exp(-log_ratio))
    reasoning = (
        f"expected_hours={expected:.2f}, actual_hours={actual:.2f}, log_ratio={log_ratio:.3f}"
    )
    return (normalized, reasoning)


def cost_rubric(workflow: Workflow) -> tuple[float, str]:
    expected_cost = sum((float(t.estimated_cost or 0.0) for t in workflow.tasks.values()))
    actual_cost = float(workflow.total_cost or 0.0)
    expected_cost = max(expected_cost, 1e-06)
    actual_cost = max(actual_cost, 1e-06)
    log_ratio = math.log(expected_cost / actual_cost)
    normalized = 1.0 / (1.0 + math.exp(-log_ratio))
    reasoning = f"expected_cost={expected_cost:.2f}, actual_cost={actual_cost:.2f}, log_ratio={log_ratio:.3f}"
    return (normalized, reasoning)


def agent_utilization_efficiency(
    workflow: Workflow, context: ValidationContext
) -> tuple[float, str]:
    """Average runtime utilization across agents: len(current_tasks)/capacity.

    Requires: AGENT_PUBLIC_STATES
    """
    try:
        states = context.agent_public_states or {}
        if not states:
            return (0.0, "no agent state")
        utilizations: list[float] = []
        for st in states.values():
            cap = max(1, int(st.max_concurrent_tasks or 1))
            cur = len(st.current_task_ids or [])
            utilizations.append(max(0.0, min(1.0, float(cur) / float(cap))))
        score = sum(utilizations) / float(len(utilizations)) if utilizations else 0.0
        return (score, f"avg_utilization={score:.2f} over {len(utilizations)} agents")
    except Exception:
        return (0.0, "error computing utilization")


def evidence_seeking_behavior(workflow: Workflow, context: ValidationContext) -> tuple[float, str]:
    """Fraction of completed tasks with at least one web search call.

    Requires: AGENT_TOOL_USAGE_BY_TASK
    """
    try:
        usage = context.agent_tool_usage_by_task or {}
        completed_task_ids = {
            tid for tid, t in workflow.tasks.items() if t.status == TaskStatus.COMPLETED
        }
        if not completed_task_ids:
            return (0.0, "no completed tasks")
        relevant = [tid for tid in usage.keys() if tid in completed_task_ids]
        if not relevant:
            return (0.0, "no tool usage on completed tasks")
        hits = 0
        for tid in relevant:
            events = usage.get(tid, [])
            if any(((e.tool_name or "").endswith("web_search.get_search_context") for e in events)):
                hits += 1
        score = float(hits) / float(len(completed_task_ids))
        score = max(0.0, min(1.0, score))
        return (score, f"evidence_tasks={hits}/{len(completed_task_ids)}")
    except Exception:
        return (0.0, "error computing evidence seeking")
