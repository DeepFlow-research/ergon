"""Evaluate a single task with one evaluator/rubric.

Invoked by check_evaluators per evaluator. Creates the criterion executor,
runs all criteria, aggregates results, persists RunTaskEvaluation.
"""

import logging
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

from ergon_core.api.benchmark import Task
from ergon_core.core.infrastructure.dashboard.provider import get_dashboard_emitter
from ergon_core.core.application.evaluation.models import TaskEvaluationContext
from ergon_core.core.application.evaluation.inngest_executor import InngestCriterionExecutor
from ergon_core.core.infrastructure.inngest.errors import ContractViolationError
from ergon_core.core.application.jobs.models import EvaluateTaskRunRequest
from ergon_core.core.application.evaluation.service import (
    EvaluationService,
)
from ergon_core.core.application.jobs.models import EvaluateTaskRunResult
from ergon_core.core.persistence.graph.models import RunGraphNode
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.infrastructure.tracing import (
    CompletedSpan,
    evaluation_task_context,
    get_trace_sink,
)
from sqlmodel import select
from typing import Any

logger = logging.getLogger(__name__)
evaluation_persistence = EvaluationService()


async def run_evaluate_task_run_job(
    ctx: Any, payload: EvaluateTaskRunRequest
) -> EvaluateTaskRunResult:
    run_id = payload.run_id
    task_id = payload.task_id
    execution_id = payload.execution_id
    evaluator_index = payload.evaluator_index
    evaluator_name = payload.evaluator_name
    agent_reasoning = payload.agent_reasoning
    span_start = datetime.now(UTC)

    with get_session() as session:
        node = session.exec(
            select(RunGraphNode).where(
                RunGraphNode.run_id == run_id,
                RunGraphNode.task_id == task_id,
            )
        ).first()
        if node is None:
            raise ContractViolationError(
                f"RunGraphNode task_id={task_id} not found",
                run_id=run_id,
                task_id=task_id,
            )
        task = Task.from_definition(node.task_json, task_id=node.task_id)

    node_id = node.id
    definition_task_id = node.definition_task_id
    try:
        evaluator = task.evaluators[evaluator_index]
    except IndexError as exc:
        raise ContractViolationError(
            f"Task {task_id} has no evaluator at index {evaluator_index}",
            run_id=run_id,
            task_id=task_id,
        ) from exc
    if evaluator.name != evaluator_name:
        logger.warning(
            "evaluate_task_run evaluator name mismatch task_id=%s index=%s payload=%s actual=%s",
            task_id,
            evaluator_index,
            evaluator_name,
            evaluator.name,
        )
    sandbox_manager = getattr(task.sandbox, "manager", object())
    evaluator_trace_id = uuid5(NAMESPACE_URL, f"{run_id}:{task_id}:evaluator:{evaluator_index}")

    executor = InngestCriterionExecutor(
        ctx,
        task_id=node_id,
        execution_id=execution_id,
        evaluator_id=evaluator_trace_id,
        sandbox_manager=sandbox_manager,
    )

    task_input = task.description
    task_context = TaskEvaluationContext(
        run_id=run_id,
        task_input=task_input,
        agent_reasoning=agent_reasoning,
        sandbox_id=payload.sandbox_id,
    )

    service = EvaluationService(criterion_executor=executor)
    try:
        service_result = await service.evaluate(
            task_context=task_context,
            evaluator=evaluator,
            task=task,
            benchmark_name="",
        )
    except Exception as exc:  # slopcop: ignore[no-broad-except]
        logger.exception(
            "evaluate_task_run failed run_id=%s task_id=%s evaluator=%s",
            run_id,
            task_id,
            evaluator_name,
        )
        evaluation_persistence.persist_failure(
            run_id=run_id,
            node_id=node_id,
            task_execution_id=execution_id,
            definition_task_id=definition_task_id,
            evaluator_index=evaluator_index,
            evaluator_name=evaluator_name,
            exc=exc,
        )
        return EvaluateTaskRunResult(
            score=0.0,
            passed=False,
            evaluator_name=evaluator_name,
        )
    result = service_result.result

    persisted = evaluation_persistence.persist_success(
        run_id=run_id,
        node_id=node_id,
        task_execution_id=execution_id,
        definition_task_id=definition_task_id,
        evaluator_index=evaluator_index,
        evaluator_name=evaluator.name,
        service_result=service_result,
    )
    await get_dashboard_emitter().task_evaluation_updated(
        run_id=run_id,
        task_id=node_id,
        evaluation=persisted.dashboard_dto,
    )

    get_trace_sink().emit_span(
        CompletedSpan(
            name="evaluation.task",
            context=evaluation_task_context(run_id, node_id, execution_id, evaluator_trace_id),
            start_time=span_start,
            end_time=datetime.now(UTC),
            attributes={
                "run_id": str(run_id),
                "task_id": str(task_id),
                "execution_id": str(execution_id),
                "evaluator_index": evaluator_index,
                "evaluator_name": evaluator.name,
                "score": result.score,
                "passed": result.passed,
                "stages_evaluated": persisted.summary.stages_evaluated,
                "stages_passed": persisted.summary.stages_passed,
            },
        )
    )

    return EvaluateTaskRunResult(
        score=result.score,
        passed=result.passed,
        evaluator_name=result.evaluator_name,
    )
