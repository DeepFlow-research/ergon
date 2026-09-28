# ruff: noqa: E501
"""Prompt templates used by the native Manager Gym adapter."""

from ergon_builtins.benchmarks.manager_gym.upstream import WorkflowRubric

# Upstream parity: the LLM judge instructions from MAG's
# ``WorkflowValidationRule._llm_validate`` (core/evaluation/validation_rules.py),
# kept word for word so LLM rubric scores stay comparable with upstream.
JUDGE_PROMPT_TEMPLATE = """
You are an LLM evaluator for multi-agent workflows.

Definition and setting:
- A workflow in this system is a structured plan of tasks, resources, and communications executed by a team of specialized agents (and sometimes humans) collaborating to achieve a stated project goal.
- The provided workflow context below contains the full, current state: goal, agents, tasks with dependencies and status, produced resources, costs, quality metrics, and communications.

Evaluation framing:
- We want to evaluate how well the workflow performed on specific aspects (e.g., quality, governance/compliance, completeness, timeliness, coordination). The VALIDATION CRITERIA below defines the exact aspect and how to judge it for this evaluation (treat it like a rubric).

Instructions:
- Carefully read the VALIDATION CRITERIA and operationalize them as checkable conditions.
- Use only the WORKFLOW CONTEXT as evidence. If evidence is missing or inconclusive, state that explicitly and score conservatively.
- Return a single field named score whose type matches what the criteria requests: boolean (true/false), a categorical level ("low" | "medium" | "high"), or a numeric value in [0, {max_score}].
- In reasoning, include brief citations to evidence from the workflow and short, actionable next steps to pass/improve.

Scoring guide for numeric scores (apply these rules uniformly):
- 0: No relevant evidence, contradictory evidence, or explicit failures against the criteria.
- 0.25×max: Minimal evidence or weak/indirect signals; at most one element satisfied with major gaps.
- 0.5×max: Partial fulfillment; roughly half of the required elements satisfied with cited evidence; notable gaps remain.
- 0.75×max: Strong fulfillment; most elements satisfied with high-quality evidence; only minor gaps or missing citations.
- 1.0×max (i.e., {max_score}): Complete fulfillment across all required elements with explicit, verifiable citations; quantitative KPIs where applicable.

Partial-credit rules when criteria enumerate elements (e.g., items (a)-(d) or bullet lists):
- Divide the maximum score evenly across the N enumerated elements.
- For each element: award 0 for absent/contradictory, 0.5 of the element share for incomplete or weak evidence, and 1.0 of the element share for clear, well-cited satisfaction.
- If evidence is entirely missing for the criterion, cap the total at 0.5×max.
- If there is contradictory evidence, reduce the total by at least 0.25×max (not below 0).

VALIDATION CRITERIA:
{criteria}

WORKFLOW CONTEXT (full):
{workflow_context}

OUTPUT REQUIREMENTS (JSON only, no prose outside JSON):
- score: true/false, "low"/"medium"/"high", or a number in [0, {max_score}] as directed by the criteria
- reasoning: 3–6 sentences with evidence-based justification and specific next steps
- confidence: number in [0,1]
"""


def judge_prompt(rubric: WorkflowRubric, workflow_context: str) -> str:
    """Render the LLM judge prompt for one rubric.

    Args:
        rubric: The upstream rubric; its ``llm_prompt`` is the grading criteria.
        workflow_context: The rendered workflow the judge grades.

    Returns:
        The prompt text sent to the judge model.
    """
    return JUDGE_PROMPT_TEMPLATE.format(
        max_score=rubric.max_score,
        criteria=rubric.llm_prompt,
        workflow_context=workflow_context,
    )
