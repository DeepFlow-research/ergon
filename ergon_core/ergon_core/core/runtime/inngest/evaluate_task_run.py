"""Evaluate a single task with one evaluator/rubric.

Invoked by check_evaluators per evaluator. Creates the criterion executor,
runs all criteria, aggregates results, persists RunTaskEvaluation.
"""

from datetime import UTC, datetime

import inngest
from ergon_builtins.registry import EVALUATORS, SANDBOX_MANAGERS
from ergon_core.core.dashboard.emitter import dashboard_emitter
from ergon_core.api.task_types import BenchmarkTask
from ergon_core.core.persistence.queries import queries
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.telemetry.evaluation_summary import (
    CriterionResultEntry,
    EvaluationSummary,
)
from ergon_core.core.persistence.telemetry.models import RunTaskEvaluation
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
from ergon_core.core.runtime.services.rubric_evaluation_service import (
    EvaluationServiceResult,
    RubricEvaluationService,
)
from ergon_core.core.runtime.tracing import (
    CompletedSpan,
    evaluation_task_context,
    get_trace_sink,
)


def _build_evaluation_summary(
    service_result: EvaluationServiceResult,
    evaluation_input: str,
) -> EvaluationSummary:
    """Build a strongly-typed evaluation summary from service result + specs."""
    result = service_result.result
    specs = service_result.specs

    spec_by_idx = {s.criterion_idx: s for s in specs}
    max_score_total = sum(s.max_score for s in specs) if specs else 1.0

    entries: list[CriterionResultEntry] = []
    for i, cr in enumerate(result.criterion_results):
        spec = spec_by_idx.get(i)
        if spec is None:
            raise ContractViolationError(
                f"Criterion result at index {i} ({cr.name!r}) has no matching "
                f"CriterionSpec — specs and results are out of sync",
            )
        entries.append(
            CriterionResultEntry(
                criterion_name=cr.name,
                criterion_type=spec.criterion.type_slug,
                criterion_description=spec.criterion.name,
                stage_num=spec.stage_idx,
                stage_name=spec.stage_name,
                criterion_num=spec.criterion_idx,
                score=cr.score,
                max_score=spec.max_score,
                passed=cr.passed,
                weight=cr.weight,
                feedback=cr.feedback or "",
                evaluation_input=evaluation_input,
            )
        )

    total_score = result.score
    normalized = total_score / max_score_total if max_score_total > 0 else 0.0

    stage_names = {s.stage_name for s in specs}
    stages_passed = sum(
        1 for sn in stage_names if all(e.passed for e in entries if e.stage_name == sn)
    )

    return EvaluationSummary(
        evaluator_name=result.evaluator_name,
        max_score=max_score_total,
        normalized_score=normalized,
        stages_evaluated=len(stage_names),
        stages_passed=stages_passed,
        criterion_results=entries,
    )


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

    task_context = TaskEvaluationContext(
        run_id=run_id,
        task_input="",
        agent_reasoning=agent_reasoning,
        sandbox_id=payload.sandbox_id,
    )

    task = BenchmarkTask(
        task_key="",
        instance_key="",
        description="",
    )

    service = RubricEvaluationService(criterion_executor=executor)
    service_result = await service.evaluate(
        task_context=task_context,
        evaluator=evaluator,
        task=task,
        benchmark_name="",
    )
    result = service_result.result

    summary = _build_evaluation_summary(service_result, evaluation_input="")

    session = get_session()
    try:
        evaluation = RunTaskEvaluation(
            run_id=run_id,
            definition_task_id=task_id,
            definition_evaluator_id=evaluator_id,
            score=result.score,
            passed=result.passed,
            feedback=result.feedback,
            summary_json=summary.model_dump(mode="json"),
        )
        session.add(evaluation)
        session.commit()
        session.refresh(evaluation)
    finally:
        session.close()

    evaluation_dict = {
        "id": str(evaluation.id),
        "runId": str(run_id),
        "taskId": str(task_id),
        "totalScore": result.score,
        "maxScore": summary.max_score,
        "normalizedScore": summary.normalized_score,
        "stagesEvaluated": summary.stages_evaluated,
        "stagesPassed": summary.stages_passed,
        "failedGate": None,
        "createdAt": evaluation.created_at.isoformat(),
        "criterionResults": [
            {
                "criterionName": cr.criterion_name,
                "criterionType": cr.criterion_type,
                "score": cr.score,
                "maxScore": cr.max_score,
                "passed": cr.passed,
                "feedback": cr.feedback,
            }
            for cr in summary.criterion_results
        ],
    }
    await dashboard_emitter.task_evaluation_updated(
        run_id=run_id,
        task_id=task_id,
        evaluation=evaluation_dict,
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
                "stages_evaluated": summary.stages_evaluated,
                "stages_passed": summary.stages_passed,
            },
        )
    )

    return EvaluateTaskRunResult(
        score=result.score,
        passed=result.passed,
        evaluator_name=result.evaluator_name,
    )
