"""Prepare evaluation payloads for task-level evaluator fanout.

Reads evaluator bindings from definition tables and task execution
outputs to build PreparedSingleEvaluator payloads.
"""

from ergon_core.core.persistence.definitions.models import (
    ExperimentDefinitionEvaluator,
    ExperimentDefinitionTask,
    ExperimentDefinitionTaskEvaluator,
)
from ergon_core.core.persistence.graph.models import RunGraphNode
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.telemetry.models import RunTaskExecution
from ergon_core.core.runtime.services.evaluation_dto import (
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
            node = session.get(RunGraphNode, command.node_id)
            if node is None:
                raise LookupError(f"run graph node not found: {command.node_id}")
            task_id = command.task_id or node.definition_task_id
            if task_id is None:
                return PreparedEvaluatorDispatch(
                    node_id=command.node_id,
                    task_id=None,
                    evaluators_found=0,
                )
            task_evals = list(
                session.exec(
                    select(ExperimentDefinitionTaskEvaluator).where(
                        ExperimentDefinitionTaskEvaluator.experiment_definition_id
                        == command.definition_id,
                        ExperimentDefinitionTaskEvaluator.task_id == task_id,
                    )
                ).all()
            )

            if not task_evals:
                return PreparedEvaluatorDispatch(
                    node_id=command.node_id,
                    task_id=task_id,
                    evaluators_found=0,
                )

            task_row = session.get(ExperimentDefinitionTask, task_id)
            if task_row is None:
                raise LookupError(f"definition task not found: {task_id}")

            execution = session.get(RunTaskExecution, command.execution_id)
            agent_reasoning = execution.final_assistant_message if execution is not None else None

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
                        task_input=task_row.description,
                        agent_reasoning=agent_reasoning,
                    )
                )

            return PreparedEvaluatorDispatch(
                node_id=command.node_id,
                task_id=task_id,
                evaluators_found=len(task_evals),
                valid_evaluators=valid_evaluators,
            )
        finally:
            session.close()
