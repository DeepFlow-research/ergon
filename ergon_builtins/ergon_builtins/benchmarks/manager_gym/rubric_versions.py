"""Rubric versions: corrections applied on top of upstream MAG's rubric definitions.

Version 1 reproduces upstream's rubrics exactly. Version 2, the default, fixes the
upstream bugs listed in ``_vendor/mag/README.md``. Corrections never edit the
vendored files; they are applied to a rubric's definition when criteria are built,
and every criterion records the version it was graded under.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from ergon_builtins.benchmarks.manager_gym.upstream import AdditionalContextItem, WorkflowRubric

RubricVersion = Literal[1, 2]
LATEST_RUBRIC_VERSION: RubricVersion = 2


class RubricCorrection(BaseModel):
    """A change to one upstream rubric, identified by scenario, owner and rubric name."""

    model_config = ConfigDict(frozen=True)

    since: RubricVersion
    scenario: str | None = None
    owner: str
    rubric: str
    exclude: bool = False
    update: dict[str, Any] = {}
    reason: str

    def matches(self, scenario: str, owner: str, rubric: WorkflowRubric) -> bool:
        return (
            self.scenario in (None, scenario) and self.owner == owner and self.rubric == rubric.name
        )


CORRECTIONS = (
    RubricCorrection(
        since=2,
        scenario="icaap",
        owner="quality",
        rubric="seeking_sourcing",
        exclude=True,
        reason="Counts web-search tool calls that no MAG runner gives workers, without "
        "requesting tool usage, and scores a 0-1 fraction against a maximum of 3, so it "
        "always scores 0 and lowers ICAAP's quality score.",
    ),
    RubricCorrection(
        since=2,
        owner="stakeholder_management",
        rubric="response_latency_adherence",
        update={
            "max_score": 8.0,
            "description": "Max 8; subtract 1 per timestep of delay in stakeholder replies to "
            "manager.",
        },
        reason="The function caps its score at 8 but the rubric declares a maximum of 20.",
    ),
    RubricCorrection(
        since=2,
        owner="operational_efficiency",
        rubric="agent_utilization_efficiency",
        update={
            "description": "Average utilisation of active agents: running tasks per unit of "
            "capacity.",
            "required_context": {AdditionalContextItem.AGENT_PUBLIC_STATES},
        },
        reason="The description is copied from deadtime_efficiency, and the rubric never "
        "requests the agent states its function reads.",
    ),
)


def corrected(
    rubric: WorkflowRubric, *, scenario: str, owner: str, version: RubricVersion
) -> WorkflowRubric | None:
    """``rubric`` as graded under ``version``, or ``None`` if that version drops it."""
    for correction in CORRECTIONS:
        if version >= correction.since and correction.matches(scenario, owner, rubric):
            if correction.exclude:
                return None
            rubric = rubric.model_copy(update=correction.update)
    return rubric
