"""Evaluate a single task with one evaluator/rubric.

Invoked by check_evaluators per evaluator. Creates the criterion executor,
runs all criteria, aggregates results, persists RunTaskEvaluation.
"""

import logging
from datetime import UTC, datetime

from ergon_core.api.benchmark import EmptyTaskPayload, Task
from ergon_core.core.application.components.catalog import ComponentCatalogService
from ergon_core.core.application.experiments.repository import DefinitionRepository
from ergon_core.core.infrastructure.dashboard.provider import get_dashboard_emitter
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.infrastructure.inngest.errors import ContractViolationError
from ergon_core.core.application.evaluation.models import TaskEvaluationContext
from ergon_core.core.application.evaluation.inngest_executor import InngestCriterionExecutor
from ergon_core.core.application.jobs.models import EvaluateTaskRunRequest
from ergon_core.core.application.evaluation.service import (
    EvaluationService,
)
from ergon_core.core.application.jobs.models import EvaluateTaskRunResult
from ergon_core.core.infrastructure.tracing import (
    CompletedSpan,
    evaluation_task_context,
    get_trace_sink,
)
from pydantic import BaseModel
from typing import Any

logger = logging.getLogger(__name__)
evaluation_persistence = EvaluationService()


async def run_evaluate_task_run_job(
    ctx: Any, payload: EvaluateTaskRunRequest
) -> EvaluateTaskRunResult:
    run_id = payload.run_id
    definition_task_id = payload.task_id
    node_id = payload.node_id
    execution_id = payload.execution_id
    evaluator_id = payload.evaluator_id
    evaluator_binding_key = payload.evaluator_binding_key
    evaluator_type = payload.evaluator_type
    agent_reasoning = payload.agent_reasoning
    span_start = datetime.now(UTC)

    catalog = ComponentCatalogService()
    definition_repo = DefinitionRepository()
    with get_session() as session:
        evaluator_cls = catalog.resolve_evaluator(session, evaluator_type)
        evaluator = evaluator_cls(name=evaluator_binding_key)
        definition = definition_repo.get(session, payload.definition_id)
        if definition is None:
            raise ContractViolationError(
                f"ExperimentDefinition {payload.definition_id} not found",
                run_id=run_id,
                task_id=node_id,
            )
        benchmark_type = definition.benchmark_type
        manager_cls = catalog.resolve_sandbox_manager(session, benchmark_type)
        benchmark_cls = catalog.resolve_benchmark(session, benchmark_type)
        if definition_task_id is None:
            raise ContractViolationError(
                "task/evaluate requires definition_task_id while evaluator bindings are definition-scoped",
                run_id=run_id,
                task_id=node_id,
            )
        task_row, instance_row = definition_repo.task_with_instance(session, definition_task_id)

    sandbox_manager = manager_cls()

    executor = InngestCriterionExecutor(
        ctx,
        task_id=node_id,
        execution_id=execution_id,
        evaluator_id=evaluator_id,
        sandbox_manager=sandbox_manager,
    )

    task_input = task_row.description
    task_context = TaskEvaluationContext(
        run_id=run_id,
        task_input=task_input,
        agent_reasoning=agent_reasoning,
        sandbox_id=payload.sandbox_id,
    )

    task_payload = task_row.task_payload_as(benchmark_cls.task_payload_model)
    task = Task[BaseModel](
        task_id=node_id,
        task_slug=task_row.task_slug,
        instance_key=instance_row.instance_key,
        description=task_input,
        task_payload=task_payload or EmptyTaskPayload(),
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
            node_id,
            evaluator_type,
        )
        evaluation_persistence.persist_failure(
            run_id=run_id,
            node_id=node_id,
            task_execution_id=execution_id,
            definition_task_id=definition_task_id,
            evaluator_id=evaluator_id,
            evaluator_name=evaluator_binding_key,
            exc=exc,
        )
        return EvaluateTaskRunResult(
            score=0.0,
            passed=False,
            evaluator_name=evaluator_binding_key,
        )
    result = service_result.result

    persisted = evaluation_persistence.persist_success(
        run_id=run_id,
        node_id=node_id,
        task_execution_id=execution_id,
        definition_task_id=definition_task_id,
        evaluator_id=evaluator_id,
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
            context=evaluation_task_context(run_id, node_id, execution_id, evaluator_id),
            start_time=span_start,
            end_time=datetime.now(UTC),
            attributes={
                "run_id": str(run_id),
                "task_id": str(node_id),
                "execution_id": str(execution_id),
                "evaluator_id": str(evaluator_id),
                "evaluator_type": evaluator_type,
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
