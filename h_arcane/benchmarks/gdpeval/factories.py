"""GDPEval factory functions for stakeholder and toolkit creation."""

from uuid import UUID

from h_arcane.core.db.models import Experiment
from h_arcane.core.infrastructure.sandbox import BaseSandboxManager
from h_arcane.benchmarks.gdpeval.stakeholder import RubricStakeholder
from h_arcane.benchmarks.gdpeval.toolkit import GDPEvalToolkit
from h_arcane.benchmarks.gdpeval.rubric import StagedRubric


def create_stakeholder(experiment: Experiment) -> RubricStakeholder:
    """Create GDPEval stakeholder from experiment."""
    rubric = StagedRubric(**experiment.ground_truth_rubric)
    return RubricStakeholder(
        ground_truth_rubric=rubric,
        task_description=experiment.task_description,
    )


def create_toolkit(
    run_id: UUID,
    experiment_id: UUID,
    stakeholder: RubricStakeholder,
    sandbox_manager: BaseSandboxManager,
    max_questions: int,
) -> GDPEvalToolkit:
    """Create GDPEval toolkit."""
    return GDPEvalToolkit(
        run_id=run_id,
        experiment_id=experiment_id,
        stakeholder=stakeholder,
        sandbox_manager=sandbox_manager,
        max_questions=max_questions,
    )
