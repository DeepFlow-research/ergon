"""ResearchRubrics factory functions for stakeholder and toolkit creation."""

from uuid import UUID

from h_arcane.core.db.models import Experiment
from h_arcane.core.infrastructure.sandbox import BaseSandboxManager
from h_arcane.benchmarks.researchrubrics.stakeholder import RubricAwareStakeholder
from h_arcane.benchmarks.researchrubrics.toolkit import ResearchRubricsToolkit


def create_stakeholder(experiment: Experiment) -> RubricAwareStakeholder:
    """Create ResearchRubrics stakeholder from experiment.

    Args:
        experiment: The experiment containing ablated prompt and rubric criteria

    Returns:
        RubricAwareStakeholder configured with the experiment's criteria
    """
    return RubricAwareStakeholder(experiment)


def create_toolkit(
    run_id: UUID,
    stakeholder: RubricAwareStakeholder,
    sandbox_manager: BaseSandboxManager,
    max_questions: int,
) -> ResearchRubricsToolkit:
    """Create ResearchRubrics toolkit.

    Args:
        run_id: The run ID for logging
        stakeholder: The stakeholder for answering questions
        sandbox_manager: Sandbox manager (not actively used for Exa tools)
        max_questions: Maximum stakeholder questions allowed

    Returns:
        ResearchRubricsToolkit configured for the run
    """
    return ResearchRubricsToolkit(
        run_id=run_id,
        stakeholder=stakeholder,
        sandbox_manager=sandbox_manager,
        max_questions=max_questions,
    )
