"""ResearchRubrics factory functions for stakeholder and toolkit creation."""

from uuid import UUID

from h_arcane.core._internal.db.models import Experiment
from h_arcane.core._internal.infrastructure.sandbox import BaseSandboxManager
from h_arcane.benchmarks.researchrubrics.stakeholder import RubricAwareStakeholder
from h_arcane.benchmarks.researchrubrics.toolkit import ResearchRubricsToolkit
from h_arcane.core.settings import settings


def create_stakeholder(experiment: Experiment) -> RubricAwareStakeholder:
    """Create ResearchRubrics stakeholder from experiment.

    Args:
        experiment: The experiment containing ablated prompt and rubric criteria

    Returns:
        RubricAwareStakeholder configured with the experiment's criteria
    """
    return RubricAwareStakeholder(experiment)


def create_toolkit(
    task_id: UUID,
    run_id: UUID,
    experiment_id: UUID,
    stakeholder: RubricAwareStakeholder,
    sandbox_manager: BaseSandboxManager,
    max_questions: int,
) -> ResearchRubricsToolkit:
    """Create ResearchRubrics toolkit.

    Args:
        task_id: UUID of the task (for sandbox keying)
        run_id: The run ID for communication service
        experiment_id: The experiment ID for communication service
        stakeholder: The stakeholder for answering questions
        sandbox_manager: Sandbox manager (not actively used for Exa tools)
        max_questions: Maximum stakeholder questions allowed

    Returns:
        ResearchRubricsToolkit configured for the run

    Raises:
        ValueError: If EXA_API_KEY is not set in settings
    """
    # Validate Exa API key is set before creating toolkit
    if not settings.exa_api_key:
        raise ValueError(
            "EXA_API_KEY is not set. ResearchRubrics requires Exa API key for web search tools. "
            "Please set EXA_API_KEY in your .env file or environment variables."
        )

    return ResearchRubricsToolkit(
        task_id=task_id,
        run_id=run_id,
        experiment_id=experiment_id,
        stakeholder=stakeholder,
        sandbox_manager=sandbox_manager,
        max_questions=max_questions,
    )
