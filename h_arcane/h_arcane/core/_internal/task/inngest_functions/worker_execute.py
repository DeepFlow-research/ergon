"""Worker execution child function.

Executes the worker agent in the sandbox using SDK types.
"""

from functools import partial
from typing import TYPE_CHECKING
from uuid import UUID

import inngest
import uuid

from h_arcane.benchmarks.enums import BenchmarkName
from h_arcane.benchmarks.registry import (
    get_sandbox_manager,
    get_stakeholder_factory,
    get_toolkit_factory,
)
from h_arcane.core._internal.agents.base import BaseStakeholder, BaseToolkit
from h_arcane.core._internal.db.models import Action, AgentConfig, ResourceRecord
from h_arcane.core._internal.db.queries import queries
from h_arcane.core._internal.infrastructure.inngest_client import inngest_client
from h_arcane.core._internal.infrastructure.tracing import (
    CompletedSpan,
    get_trace_sink,
    safe_json_attribute,
    tool_action_context,
    truncate_text,
    worker_execute_context,
)
from h_arcane.core._internal.infrastructure.sandbox import BaseSandboxManager
from h_arcane.core._internal.task.requests import WorkerExecuteRequest
from h_arcane.core._internal.task.results import WorkerExecuteResult
from h_arcane.core._internal.task.worker_context import get_worker
from h_arcane.core._internal.task.conversions import db_resources_to_sdk
from h_arcane.core._internal.utils import require_not_none, utcnow
from h_arcane.core.worker import WorkerContext, WorkerResult, BaseWorker
from h_arcane.core.task import Task
from h_arcane.core.dashboard import dashboard_emitter

if TYPE_CHECKING:
    from h_arcane.core._internal.db.models import Experiment


# ============================================================================
# Inngest Function (orchestrator)
# ============================================================================


@inngest_client.create_function(
    fn_id="worker-execute",
    trigger=inngest.TriggerEvent(event=WorkerExecuteRequest.name),
    retries=0,  # Worker execution should not auto-retry
    output_type=WorkerExecuteResult,
)
async def worker_execute_fn(ctx: inngest.Context) -> WorkerExecuteResult:
    """
    Execute the worker agent in the sandbox.

    This child function:
    1. Loads input resources and experiment context
    2. Sets up stakeholder and toolkit
    3. Creates worker and executes task
    4. Returns execution result
    """
    payload = WorkerExecuteRequest.model_validate(ctx.event.data)
    run_id = payload.run_id
    task_id = payload.task_id
    benchmark_name = BenchmarkName(payload.benchmark_name)

    # Load context (inlined - pure reads)
    run = require_not_none(queries.runs.get(run_id), f"Run {run_id} not found")
    experiment = require_not_none(
        queries.experiments.get(run.experiment_id),
        f"Experiment {run.experiment_id} not found",
    )

    # Load input resources by IDs
    input_resources = [
        require_not_none(queries.resources.get(rid), f"Resource {rid} not found")
        for rid in payload.input_resource_ids
    ]

    # Get benchmark-specific factories
    sandbox_manager = get_sandbox_manager(benchmark_name)
    stakeholder_factory = get_stakeholder_factory(benchmark_name)
    toolkit_factory = get_toolkit_factory(benchmark_name)

    # Create stakeholder and toolkit (with task_id for sandbox keying)
    stakeholder: BaseStakeholder = stakeholder_factory(experiment)
    toolkit: BaseToolkit = toolkit_factory(
        task_id=task_id,
        run_id=run_id,
        experiment_id=experiment.id,
        stakeholder=stakeholder,
        sandbox_manager=sandbox_manager,
        max_questions=payload.max_questions,
    )

    # Get worker from context (stored during execute_task)
    worker = get_worker(task_id)
    execution_id = payload.execution_id

    # Get or create worker agent config (deduplicated by worker_id)
    agent_config = await ctx.step.run(
        "get-or-create-worker-config",
        partial(_get_or_create_worker_config, run_id, worker),
        output_type=AgentConfig,
    )
    if agent_config is None:
        raise ValueError("Failed to get or create worker agent config")

    # Link execution to agent (Solution 3: fixes TaskExecution.agent_id NULL)
    await ctx.step.run(
        "link-execution-to-agent",
        partial(_link_execution_to_agent, execution_id, agent_config.id),
    )

    # Get or create stakeholder agent config (deduplicated by deterministic ID)
    await ctx.step.run(
        "get-or-create-stakeholder-config",
        partial(_get_or_create_stakeholder_config, run_id, benchmark_name, stakeholder),
        output_type=AgentConfig,
    )

    # Execute worker
    result = await _execute_worker(
        run_id=run_id,
        task_id=task_id,
        execution_id=execution_id,
        experiment=experiment,
        task_description=payload.task_description,
        agent_config=agent_config,
        worker=worker,
        toolkit=toolkit,
        sandbox_manager=sandbox_manager,
        input_resources=input_resources,
    )

    return result


async def _link_execution_to_agent(execution_id: UUID, agent_id: UUID) -> None:
    """Link a task execution to the agent that performed it."""
    queries.task_executions.set_agent(execution_id, agent_id)


async def _get_or_create_worker_config(run_id: UUID, worker: BaseWorker) -> AgentConfig:
    """Get existing worker config or create new one.

    Uses get_or_create to prevent duplicate configs for the same worker in a run.
    """
    config, _created = queries.agent_configs.get_or_create(
        run_id=run_id,
        worker_id=worker.id,
        defaults=AgentConfig(
            name=worker.name,
            agent_type="react_worker",
            role="worker",
            model=worker.model,
            system_prompt=worker.system_prompt,
            tools=[t.name if hasattr(t, "name") else str(t) for t in worker.tools],
        ),
    )
    return config


async def _get_or_create_stakeholder_config(
    run_id: UUID, benchmark_name: BenchmarkName, stakeholder: BaseStakeholder
) -> AgentConfig:
    """Get existing stakeholder config or create new one.

    Uses get_or_create to prevent duplicate configs for the same stakeholder in a run.
    Generates a deterministic stakeholder_id based on run_id and benchmark_name.
    """
    # Generate deterministic ID for stakeholder (one per run+benchmark)
    stakeholder_id = uuid.uuid5(run_id, f"stakeholder:{benchmark_name.value}")

    stakeholder_display_name = benchmark_name.value.title()
    config, _created = queries.agent_configs.get_or_create(
        run_id=run_id,
        worker_id=stakeholder_id,  # Use deterministic ID for dedup
        defaults=AgentConfig(
            name=f"{stakeholder_display_name} Stakeholder",
            agent_type="stakeholder",
            role="stakeholder",
            model=stakeholder.model,
            system_prompt=stakeholder.system_prompt,
            tools=[],
        ),
    )
    return config


async def _execute_worker(
    run_id: UUID,
    task_id: UUID,
    execution_id: UUID,
    experiment: "Experiment",
    task_description: str,
    agent_config: AgentConfig,
    worker: BaseWorker,
    toolkit: BaseToolkit,
    sandbox_manager: BaseSandboxManager,
    input_resources: list[ResourceRecord],
) -> WorkerExecuteResult:
    """Execute worker agent, persist actions, emit dashboard agent_action_completed events."""
    trace_sink = get_trace_sink()
    trace_context = worker_execute_context(
        run_id,
        task_id,
        execution_id,
        attributes={
            "experiment_id": experiment.id,
            "agent_config_id": agent_config.id,
            "worker_name": worker.name,
            "worker_model": worker.model,
        },
    )
    started_at = utcnow()
    try:
        # Build SDK WorkerContext with toolkit for workers that need it
        sdk_resources = db_resources_to_sdk(input_resources)
        sandbox = sandbox_manager.get_sandbox(run_id)
        benchmark_name = BenchmarkName(experiment.benchmark_name)

        context = WorkerContext(
            task_id=task_id,
            run_id=run_id,
            sandbox=sandbox,
            input_resources=sdk_resources,
            toolkit=toolkit,  # Workers can self-configure from context
            agent_config_id=agent_config.id,
            metadata={
                "benchmark_name": benchmark_name.value,
                "experiment_id": experiment.id,
            },
            trace_context=trace_context,
            trace_sink=trace_sink,
        )

        # Get task name from task tree (if available)
        task_name = f"task_{task_id}"
        if experiment.task_tree:
            tree = experiment.parsed_task_tree()
            if tree:
                task_node = tree.find_by_id(task_id)
                if task_node:
                    task_name = task_node.name

        # Build SDK Task
        task = Task(
            id=task_id,
            name=task_name,
            description=task_description,
            assigned_to=worker,
            resources=sdk_resources,
        )

        # Call worker with SDK types
        result: WorkerResult = await worker.execute(task, context)

        trace_sink.emit_span(
            CompletedSpan(
                name="worker.execute",
                context=trace_context,
                start_time=started_at,
                end_time=utcnow(),
                attributes={
                    "success": result.success,
                    "question_count": len(result.qa_exchanges),
                    "action_count": len(result.actions),
                    "output_count": len(result.outputs),
                },
                status_code="ok" if result.success else "error",
                status_message=result.error,
            )
        )

        # Persist actions (already complete with run_id/agent_id) and emit dashboard events
        persist_actions_started_at = utcnow()
        for action in result.actions:
            # Actions are now created complete by worker - no mutation needed
            queries.actions.create(action)
            _emit_tool_span(trace_context, execution_id, task_id, run_id, action)

            await dashboard_emitter.agent_action_completed(
                run_id=run_id,
                task_id=task_id,
                action_id=action.id,
                worker_id=agent_config.id,
                action_type=action.action_type,
                duration_ms=action.duration_ms,
                success=action.success,
                action_output=action.output,
                error=str(action.error) if action.error else None,
            )
        trace_sink.emit_span(
            CompletedSpan(
                name="worker.persist_actions",
                context=trace_sink.child_context(
                    trace_context,
                    span_key="worker.persist_actions",
                ),
                start_time=persist_actions_started_at,
                end_time=utcnow(),
                attributes={
                    "action_count": len(result.actions),
                    "dashboard_emit_count": len(result.actions),
                },
            )
        )

        run = queries.runs.get(run_id)
        if run is not None:
            queries.runs.update(
                run.model_copy(
                    update={
                        "questions_asked": (run.questions_asked or 0)
                        + (toolkit.questions_asked if hasattr(toolkit, "questions_asked") else 0)
                    }
                )
            )

        return WorkerExecuteResult(
            success=result.success,
            output_text=result.output_text,
            questions_asked=toolkit.questions_asked if hasattr(toolkit, "questions_asked") else 0,
            error=result.error,
        )
    except Exception as e:
        trace_sink.emit_span(
            CompletedSpan(
                name="worker.execute",
                context=trace_context,
                start_time=started_at,
                end_time=utcnow(),
                attributes={"success": False, "error": str(e)},
                status_code="error",
                status_message=str(e),
            )
        )
        return WorkerExecuteResult(
            success=False,
            error=str(e),
            questions_asked=toolkit.questions_asked if hasattr(toolkit, "questions_asked") else 0,
        )


def _emit_tool_span(
    parent_context,
    execution_id: UUID,
    task_id: UUID,
    run_id: UUID,
    action: Action,
) -> None:
    trace_sink = get_trace_sink()
    start_time = action.started_at
    end_time = action.completed_at or action.started_at
    trace_sink.emit_span(
        CompletedSpan(
            name=f"tool.{action.action_type}",
            context=tool_action_context(
                run_id,
                task_id,
                execution_id,
                action.id,
                attributes={"worker_action_num": action.action_num},
            ),
            start_time=start_time,
            end_time=end_time,
            attributes={
                "action_id": action.id,
                "action_num": action.action_num,
                "action_type": action.action_type,
                "duration_ms": action.duration_ms,
                "success": action.success,
                "agent_total_tokens": action.agent_total_tokens,
                "agent_total_cost_usd": action.agent_total_cost_usd,
                "input": truncate_text(action.input),
                "output": truncate_text(action.output),
                "error": safe_json_attribute(action.error) if action.error else None,
            },
            status_code="ok" if action.success else "error",
            status_message=safe_json_attribute(action.error) if action.error else None,
        )
    )
