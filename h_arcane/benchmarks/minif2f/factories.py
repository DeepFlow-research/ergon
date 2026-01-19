"""MiniF2F factory functions for stakeholder and toolkit creation."""

from uuid import UUID

from h_arcane.core._internal.db.models import Experiment
from h_arcane.core._internal.infrastructure.sandbox import BaseSandboxManager
from h_arcane.benchmarks.minif2f.stakeholder import MiniF2FStakeholder
from h_arcane.benchmarks.minif2f.toolkit import MiniF2FToolkit


def create_stakeholder(experiment: Experiment) -> MiniF2FStakeholder:
    """Create MiniF2F stakeholder from experiment."""
    ground_truth_proof = experiment.benchmark_specific_data.get("ground_truth_proof", "")
    return MiniF2FStakeholder(
        ground_truth_proof=ground_truth_proof,
        problem_statement=experiment.task_description,
    )


def create_toolkit(
    task_id: UUID,
    run_id: UUID,
    experiment_id: UUID,
    stakeholder: MiniF2FStakeholder,
    sandbox_manager: BaseSandboxManager,
    max_questions: int,
) -> MiniF2FToolkit:
    """Create MiniF2F toolkit.

    Args:
        task_id: UUID of the task (for sandbox keying)
        run_id: UUID of the run (for communication service)
        experiment_id: UUID of the experiment (for communication service)
        stakeholder: The stakeholder for Q&A
        sandbox_manager: The sandbox manager for skill execution
        max_questions: Maximum number of questions allowed
    """
    return MiniF2FToolkit(
        task_id=task_id,
        run_id=run_id,
        experiment_id=experiment_id,
        stakeholder=stakeholder,
        sandbox_manager=sandbox_manager,
        max_questions=max_questions,
    )
