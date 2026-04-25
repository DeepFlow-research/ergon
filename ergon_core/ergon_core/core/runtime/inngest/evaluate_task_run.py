"""Evaluate a single task with one evaluator/rubric.

Invoked by check_evaluators per evaluator. Creates the criterion executor,
runs all criteria, aggregates results, persists RunTaskEvaluation.
"""

from datetime import UTC, datetime
import logging

import inngest
from ergon_builtins.registry import BENCHMARKS, EVALUATORS, SANDBOX_MANAGERS
from ergon_core.core.dashboard.emitter import dashboard_emitter
from ergon_core.api.task_types import BenchmarkTask
from ergon_core.core.persistence.queries import queries
from ergon_core.core.providers.sandbox.manager import DefaultSandboxManager
from ergon_core.core.runtime.errors import ContractViolationError, RegistryLookupError
from ergon_core.core.runtime.evaluation.evaluation_schemas import TaskEvaluationContext
from ergon_core.core.runtime.evaluation.inngest_executor import InngestCriterionExecutor
from ergon_core.core.runtime.inngest_client import RUN_CANCEL, inngest_client
from ergon_core.core.runtime.services.child_function_payloads import (
    EvaluateTaskRunRequest,
)
from ergon_core.core.runtime.services.inngest_function_results import (
    EvaluateTaskRunResult,
)
from ergon_core.core.runtime.services.evaluation_persistence_service import (
    EvaluationPersistenceService,
)
from ergon_core.core.runtime.services.rubric_evaluation_service import (
    RubricEvaluationService,
)
from ergon_core.core.runtime.tracing import (
    CompletedSpan,
    evaluation_task_context,
    get_trace_sink,
)

logger = logging.getLogger(__name__)
evaluation_persistence = EvaluationPersistenceService()


@inngest_client.create_function(
    fn_id="evaluate-task-run",
    trigger=inngest.TriggerEvent(event="task/evaluate"),
    cancel=RUN_CANCEL,
    retries=1,
    output_type=EvaluateTaskRunResult,
)
async def evaluate_task_run(ctx: inngest.Context) -> EvaluateTaskRunResult:
    payload = EvaluateTaskRunRequest.model_validate(ctx.event.data)
    run_id = payload.run_id
    task_id = payload.task_id
    execution_id = payload.execution_id
    evaluator_id = payload.evaluator_id
    evaluator_binding_key = payload.evaluator_binding_key
    evaluator_type = payload.evaluator_type
    agent_reasoning = payload.agent_reasoning
    span_start = datetime.now(UTC)

    if task_id is None:
        raise ContractViolationError("EvaluateTaskRunRequest.task_id is required")
    if evaluator_binding_key is None:
        raise ContractViolationError("EvaluateTaskRunRequest.evaluator_binding_key is required")

    evaluator_cls = EVALUATORS.get(evaluator_type)
    if evaluator_cls is None:
        raise RegistryLookupError(
            "evaluator",
            evaluator_type,
            run_id=run_id,
            task_id=task_id,
        )

    evaluator = evaluator_cls(name=evaluator_binding_key)

    # Resolve the benchmark-specific sandbox manager so criteria that need a
    # runtime (LLM judge, sandbox exec) always receive one.  Falls back to
    # ``DefaultSandboxManager`` for benchmarks that don't register a custom
    # one.  The manager is a singleton per class, so this doesn't spin up a
    # new instance per evaluation.
    definition = queries.definitions.get(payload.definition_id)
    benchmark_type = definition.benchmark_type if definition is not None else None
    manager_cls = (
        SANDBOX_MANAGERS.get(benchmark_type, DefaultSandboxManager)
        if benchmark_type is not None
        else DefaultSandboxManager
    )
    sandbox_manager = manager_cls()

    executor = InngestCriterionExecutor(
        ctx,
        task_id=task_id,
        execution_id=execution_id,
        evaluator_id=evaluator_id,
        sandbox_manager=sandbox_manager,
    )

    task_row, instance_row = queries.definitions.get_task_with_instance(task_id)

    task_input = task_row.description
    task_context = TaskEvaluationContext(
        run_id=run_id,
        task_input=task_input,
        agent_reasoning=agent_reasoning,
        sandbox_id=payload.sandbox_id,
    )

    benchmark_cls = BENCHMARKS.get(benchmark_type) if benchmark_type is not None else None
    task_payload = (
        benchmark_cls.parse_task_payload(task_row.task_payload)
        if benchmark_cls is not None
        else None
    )
    task_kwargs = {
        "task_slug": task_row.task_slug,
        "instance_key": instance_row.instance_key,
        "description": task_input,
    }
    if task_payload is not None:
        task_kwargs["task_payload"] = task_payload
        task_model = BenchmarkTask[type(task_payload)]
    else:
        task_model = BenchmarkTask
    task = task_model(**task_kwargs)

    service = RubricEvaluationService(criterion_executor=executor)
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
            evaluator_type,
        )
        evaluation_persistence.persist_failure(
            run_id=run_id,
            task_id=task_id,
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
        task_id=task_id,
        evaluator_id=evaluator_id,
        service_result=service_result,
    )
    await dashboard_emitter.task_evaluation_updated(
        run_id=run_id,
        task_id=task_id,
        evaluation=persisted.dashboard_dto,
    )

    get_trace_sink().emit_span(
        CompletedSpan(
            name="evaluation.task",
            context=evaluation_task_context(run_id, task_id, execution_id, evaluator_id),
            start_time=span_start,
            end_time=datetime.now(UTC),
            attributes={
                "run_id": str(run_id),
                "task_id": str(task_id),
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

