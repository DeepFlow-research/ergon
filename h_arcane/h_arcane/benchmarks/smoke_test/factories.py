"""Smoke test factory functions for stakeholder and toolkit creation."""

from uuid import UUID

from h_arcane.core._internal.db.models import Experiment
from h_arcane.core._internal.infrastructure.sandbox import BaseSandboxManager
from h_arcane.benchmarks.smoke_test.stakeholder import MockStakeholder
from h_arcane.benchmarks.smoke_test.toolkit import SmokeTestToolkit


def create_stakeholder(experiment: Experiment) -> MockStakeholder:
    """Create smoke test stakeholder from experiment.

    Args:
        experiment: The experiment record (not used - mock stakeholder
                   returns canned responses regardless of task context)

    Returns:
        MockStakeholder instance with canned responses
    """
    return MockStakeholder()


def create_toolkit(
    task_id: UUID,
    run_id: UUID,
    experiment_id: UUID,
    stakeholder: MockStakeholder,
    sandbox_manager: BaseSandboxManager,
    max_questions: int,
) -> SmokeTestToolkit:
    """Create smoke test toolkit.

    Args:
        task_id: UUID of the task (for consistency with other toolkits)
        run_id: UUID of the run (for communication service)
        experiment_id: UUID of the experiment (for communication service)
        stakeholder: The mock stakeholder for Q&A
        sandbox_manager: The sandbox manager (not used - stub tools)
        max_questions: Maximum number of questions allowed
    """
    return SmokeTestToolkit(
        task_id=task_id,
        run_id=run_id,
        experiment_id=experiment_id,
        stakeholder=stakeholder,
        sandbox_manager=sandbox_manager,
        max_questions=max_questions,
    )
