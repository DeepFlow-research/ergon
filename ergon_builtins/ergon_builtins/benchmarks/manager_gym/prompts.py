# ruff: noqa: E501
"""Prompt text used by the native Manager Gym adapter.

Templates marked "Upstream parity" are MAG's own wording, copied from the named
upstream module; the rest are Ergon's. MAG's scenario, manager and worker prompt
templates that are vendored verbatim are imported from ``upstream.py`` instead.
"""

from ergon_builtins.benchmarks.manager_gym.upstream import WorkflowRubric

# ── Manager ──────────────────────────────────────────────────────────────────

# Appended to upstream's structured manager system prompt: how native scheduling
# differs from upstream's engine ticks.
MANAGER_SCHEDULING_RULES = "\nNative scheduling rules: assign prerequisite leaves first, then dependents. Assign only leaf tasks. Actor capacity is informational; only task dependencies constrain execution. Mutate/remove only unstarted work. Queries and invalid actions consume decisions. Noop yields briefly for running work. The episode drains admitted tasks before scoring."

DECOMPOSITION_SYSTEM_PROMPT = "Decompose the supplied task into the requested structured plan."
DECOMPOSITION_GOAL_SUFFIX = "\n\nWorkflow goal: {goal}"
DECOMPOSED_SUBTASK_DESCRIPTION = "Executive summary: {executive_summary}\nImplementation plan: {implementation_plan}\nAcceptance criteria: {acceptance_criteria}"

# Upstream parity: RandomManagerV2's one-shot assignment prompt
# (core/manager_agent/random_manager.py).
BULK_ASSIGNMENT_SYSTEM_PROMPT = (
    "You are a workflow orchestration manager operating on a task DAG.\n"
    "Goal: assign each task to the best-fit agent so work can proceed without further input.\n"
    "Respect constraints and practical roles: prefer AI agents for analysis/automation;\n"
    "route approvals, governance, and sign-offs to human/stakeholder roles when required.\n"
    "Maximize overall workflow throughput and quality; avoid leaving tasks unassigned.\n"
    "Output exactly one AssignTasksToAgentsAction with a complete 'assignments' list.\n"
)

# ── Stakeholder (scripted between decisions) ─────────────────────────────────

# Upstream parity: StakeholderAgent's scripted messages
# (core/workflow_agents/stakeholder_agent.py).
STAKEHOLDER_REPLY = (
    "Thanks for the update. My priorities remain as discussed; please proceed accordingly."
)
STAKEHOLDER_REPLY_QUOTE = "\nRegarding your message: {content}"
STAKEHOLDER_SUGGESTION = "Suggestion from {name} ({role}): Please prioritize critical-path tasks and ensure stakeholder review before final delivery."

# ── Work roles ───────────────────────────────────────────────────────────────

# Upstream parity: HumanAgent's prompts (core/workflow_agents/human_agent.py),
# kept byte for byte, including their indentation.
HUMAN_ESTIMATOR_SYSTEM_PROMPT = (
    "\n"
    "                You are {role} with {experience_years} years of experience.\n"
    "                                \n"
    "                Your task is to estimate how long it would take YOU SPECIFICALLY to complete the given task.\n"
    "                Consider:\n"
    "                - Your background: {background}\n"
    "                - Your expertise areas: {expertise_areas}\n"
    "                - Your work style: {work_style}\n"
    "                - Your personality traits: {personality_traits}\n"
    "                - Realistic time for research, planning, execution, and review\n"
    "                - Potential challenges you might face given your background\n"
    "\n"
    "                Be realistic - include time for breaks, getting up to speed, and potential obstacles.\n"
    '                Don\'t just estimate the "ideal" time, but the real time it would take you personally.'
)
HUMAN_ESTIMATOR_PROMPT = (
    "Task: {task_description}\n"
    "\n"
    "                Please estimate how many hours this task would take you to complete, considering your specific background and experience level.\n"
    "\n"
    "                Provide your reasoning and estimated hours.\n"
    "            "
)
HUMAN_TASK_PROMPT = (
    "{base_prompt}\n"
    "\n"
    "{quality_context}\n"
    "\n"
    "Please complete this task using your expertise in {expertise_areas}. \n"
    "Apply your {work_style} work style and {experience_years} years of experience.\n"
    "\n"
    "Work through this step-by-step as you naturally would, using your available tools and taking breaks as needed.\n"
)
HUMAN_MISUNDERSTOOD_TASK_PROMPT = (
    "{base_prompt}\n"
    "\n"
    "Important twist: You slightly misunderstand the task in a realistic, plausible way a human might.\n"
    "- Pick one reasonable misinterpretation (e.g., focusing on format over substance, optimizing the wrong KPI, solving a related-but-different problem, or assuming a different audience).\n"
    "- Proceed confidently without flagging confusion. Do not state that you misunderstood.\n"
    "- Produce a complete work product consistent with that misunderstanding.\n"
    "- Demonstrate craftsmanship appropriate to your background and work style.\n"
    "\n"
    "Deliver the output as you normally would for this task, fully believing it satisfies the request.\n"
)
HUMAN_TIRED_NOTE = "\n(Note: You're feeling a bit tired/stressed today)"
HUMAN_SHARP_NOTE = "\n(Note: You're feeling sharp and focused today)"
HUMAN_NO_RESOURCES = "No specific resources provided"
HUMAN_EXECUTION_NOTES = (
    "Human worker: {name}",
    "Work style: {work_style}",
    "Experience: {experience_years} years",
    "Current fatigue level: {fatigue:.2f}",
    "Quality modifier applied: {quality:.2f}",
)
HUMAN_MISUNDERSTANDING_EXECUTION_NOTES = (
    "Task execution under a subtle misunderstanding of requirements",
    "Output may be misaligned with the original intent",
)

# Upstream parity: how AIAgent and HumanAgent list input resources.
INPUT_RESOURCE_LINE = "- {name}: {description}\n  Content: {preview}"
# Upstream parity: AIAgent's fallback when the model returns no resource
# (core/workflow_agents/ai_agent.py).
FALLBACK_RESOURCE_NAME = "Completed: {task_name}"
FALLBACK_RESOURCE_DESCRIPTION = "AI agent completed task: {task_description}"

STAKEHOLDER_WORK_PERSONA = "\nReview and approval persona: {persona_description}; strictness {strictness}. Private priorities: {priorities}"

# ── Judge ────────────────────────────────────────────────────────────────────

# Upstream parity: core/evaluation/validation_rules.py.
JUDGE_SYSTEM_PROMPT = "You are a validation expert."

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
