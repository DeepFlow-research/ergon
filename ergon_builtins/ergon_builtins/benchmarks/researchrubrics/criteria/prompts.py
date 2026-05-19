"""Prompt construction for ResearchRubrics criteria."""

from ergon_core.api.criterion import CriterionContext

from ergon_builtins.benchmarks.researchrubrics.criteria.evidence import ResourceEvidence
from ergon_builtins.benchmarks.researchrubrics.task_schemas import RubricCriterion


def build_system_prompt(criterion: RubricCriterion) -> str:
    axis_context = (
        f"\n\nThis criterion belongs to the ResearchRubrics '{criterion.axis}' axis."
        if criterion.axis
        else ""
    )
    weight_note = f"\n\nResearchRubrics weight: {criterion.weight}"
    return (
        "You are an expert ResearchRubrics evaluator assessing deep-research reports.\n\n"
        "Evaluate whether the report satisfies this exact rubric criterion:\n"
        f"{criterion.criterion}{axis_context}{weight_note}\n\n"
        "Judge the final output resources first. Use scratch/supporting resources "
        "only as secondary context, and use the final assistant message only as a "
        "status summary. Return a binary verdict: `passed=true` only when the "
        "criterion is clearly satisfied. Explain the decision with concrete "
        "evidence from the provided material."
    )


def build_user_prompt(
    context: CriterionContext,
    *,
    final_outputs: list[ResourceEvidence],
    scratch_outputs: list[ResourceEvidence],
) -> str:
    return "\n\n".join(
        [
            f"Original research request:\n{context.task.description}",
            format_resource_section("Final output resources", final_outputs),
            format_resource_section("Scratch / supporting resources", scratch_outputs),
            f"Final assistant message:\n{context.worker_result.output}",
        ]
    )


def format_resource_section(
    title: str,
    evidence: list[ResourceEvidence],
) -> str:
    if not evidence:
        return f"{title}:\n(none)"

    parts = [f"{title}:"]
    for idx, item in enumerate(evidence, start=1):
        resource = item.resource
        sandbox_origin = resource.metadata.get("sandbox_origin")
        provenance = (
            f"id={resource.id}; name={resource.name}; kind={resource.kind.value}; "
            f"sandbox_origin={sandbox_origin or '(unknown)'}"
        )
        parts.append(f"\n[{idx}] {provenance}\n{item.text}")
    return "\n".join(parts)
