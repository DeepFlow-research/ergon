"""Prepare evaluation payloads for task-level evaluator fanout.

Reads evaluator bindings from definition tables and task execution
outputs to build PreparedSingleEvaluator payloads.
"""

from h_arcane.core.persistence.definitions.models import (
    ExperimentDefinitionEvaluator,
    ExperimentDefinitionTaskEvaluator,
)
from h_arcane.core.persistence.shared.db import get_session
from h_arcane.core.persistence.telemetry.models import RunTaskExecution
from h_arcane.core.runtime.services.evaluation_dto import (
    DispatchEvaluatorsCommand,
    PreparedEvaluatorDispatch,
    PreparedSingleEvaluator,
)
from sqlmodel import select


class EvaluatorDispatchService:
    """Prepare evaluation payloads from definition rows + task execution outputs."""

    def prepare_dispatch(self, command: DispatchEvaluatorsCommand) -> PreparedEvaluatorDispatch:
        session = get_session()
        try:
            task_evals = list(
                session.exec(
                    select(ExperimentDefinitionTaskEvaluator).where(
                        ExperimentDefinitionTaskEvaluator.experiment_definition_id
                        == command.definition_id,
                        ExperimentDefinitionTaskEvaluator.task_id == command.task_id,
                    )
                ).all()
            )

            if not task_evals:
                return PreparedEvaluatorDispatch(
                    task_id=command.task_id,
                    evaluators_found=0,
                )

            execution = session.get(RunTaskExecution, command.execution_id)
            agent_reasoning = execution.output_text or "" if execution else ""

            valid_evaluators: list[PreparedSingleEvaluator] = []
            for te in task_evals:
                evaluator_def = session.exec(
                    select(ExperimentDefinitionEvaluator).where(
                        ExperimentDefinitionEvaluator.experiment_definition_id
                        == command.definition_id,
                        ExperimentDefinitionEvaluator.binding_key == te.evaluator_binding_key,
                    )
                ).first()

                if evaluator_def is None:
                    continue

                valid_evaluators.append(
                    PreparedSingleEvaluator(
                        evaluator_id=evaluator_def.id,
                        evaluator_binding_key=te.evaluator_binding_key,
                        evaluator_type=evaluator_def.evaluator_type,
                        task_input="",
                        agent_reasoning=agent_reasoning,
                    )
                )

            return PreparedEvaluatorDispatch(
                task_id=command.task_id,
                evaluators_found=len(task_evals),
                valid_evaluators=valid_evaluators,
            )
        finally:
            session.close()
