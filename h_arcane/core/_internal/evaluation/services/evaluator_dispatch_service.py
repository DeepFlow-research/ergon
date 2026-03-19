"""Application service for evaluator dispatch preparation."""

from __future__ import annotations

from uuid import UUID

from h_arcane.core._internal.db.queries import queries
from h_arcane.core._internal.evaluation.services.dto import (
    DispatchEvaluatorsCommand,
    PreparedEvaluatorDispatch,
    PreparedSingleEvaluator,
)


class EvaluatorDispatchService:
    """Prepare evaluation payloads for task-level rubric fanout."""

    def prepare_dispatch(
        self, command: DispatchEvaluatorsCommand
    ) -> PreparedEvaluatorDispatch:
        evaluators = queries.task_evaluators.get_by_task(command.run_id, command.task_id)
        if not evaluators:
            return PreparedEvaluatorDispatch(
                task_id=command.task_id,
                evaluators_found=0,
                invalid_evaluator_ids=[],
                valid_evaluators=[],
            )

        execution = queries.task_executions.get(command.execution_id)
        if execution is None:
            raise ValueError(f"Task execution {command.execution_id} not found")

        outputs = list(queries.resources.get_outputs_for_execution(command.execution_id))
        experiment = queries.experiments.get(command.experiment_id)
        if experiment is None:
            raise ValueError(f"Experiment {command.experiment_id} not found")

        tree = experiment.parsed_task_tree()
        task_node = tree.find_by_id(command.task_id) if tree else None
        task_input = task_node.description if task_node else ""
        agent_reasoning = execution.output_text or ""

        invalid_evaluator_ids: list[UUID] = []
        valid_evaluators: list[PreparedSingleEvaluator] = []
        for evaluator in evaluators:
            try:
                rubric = evaluator.parsed_evaluator()
            except ValueError:
                invalid_evaluator_ids.append(evaluator.id)
                continue

            valid_evaluators.append(
                PreparedSingleEvaluator(
                    evaluator_id=evaluator.id,
                    rubric=rubric,
                    task_input=task_input,
                    agent_reasoning=agent_reasoning,
                    agent_outputs=outputs,
                )
            )

        return PreparedEvaluatorDispatch(
            task_id=command.task_id,
            evaluators_found=len(evaluators),
            invalid_evaluator_ids=invalid_evaluator_ids,
            valid_evaluators=valid_evaluators,
        )
