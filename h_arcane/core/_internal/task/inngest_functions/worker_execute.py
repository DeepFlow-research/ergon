"""Worker execution child function.

Executes the worker agent in the sandbox.
"""

import inngest
from inngest_agents import set_step

from h_arcane.benchmarks.enums import BenchmarkName
from h_arcane.benchmarks.registry import (
    get_sandbox_manager,
    get_stakeholder_factory,
    get_toolkit_factory,
)
from h_arcane.core._internal.agents.base import BaseStakeholder, BaseToolkit
from h_arcane.core._internal.db.models import AgentConfig
from h_arcane.core._internal.db.queries import queries
from h_arcane.core._internal.infrastructure.inngest_client import inngest_client
from h_arcane.core._internal.task.requests import WorkerExecuteRequest
from h_arcane.core._internal.task.results import WorkerExecuteResult
from h_arcane.core._internal.task.worker_context import get_worker
from h_arcane.core._internal.utils import require_not_none


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

    # Create stakeholder and toolkit
    stakeholder: BaseStakeholder = stakeholder_factory(experiment)
    toolkit: BaseToolkit = toolkit_factory(
        run_id,
        experiment.id,
        stakeholder,
        sandbox_manager,
        payload.max_questions,
    )

    # Create stakeholder agent config (DB write, needs step)
    async def create_stakeholder_config() -> AgentConfig:
        stakeholder_display_name = benchmark_name.value.title()
        return queries.agent_configs.create(
            AgentConfig(
                run_id=run_id,
                name=f"{stakeholder_display_name} Stakeholder",
                agent_type="stakeholder",
                model=stakeholder.model,
                system_prompt=stakeholder.system_prompt,
                tools=[],
            )
        )

    await ctx.step.run(
        "create-stakeholder-config", create_stakeholder_config, output_type=AgentConfig
    )

    # Upload input resources to sandbox
    await sandbox_manager.upload_inputs(run_id, input_resources)

    # Set step context for durable tools
    set_step(ctx.step)

    # Get worker from context (stored during execute_task)
    worker = get_worker(task_id)

    async def execute() -> WorkerExecuteResult:
        try:
            exec_out = await worker.execute(
                run_id=run_id,
                task_description=payload.task_description,
                input_resources=input_resources,
                toolkit=toolkit,
            )
            return WorkerExecuteResult(
                success=True,
                output_text=exec_out.output_text,
                questions_asked=toolkit.questions_asked,
            )
        except Exception as e:
            return WorkerExecuteResult(
                success=False,
                error=str(e),
                questions_asked=toolkit.questions_asked,
            )

    result = await ctx.step.run("execute-worker", execute, output_type=WorkerExecuteResult)
    if result is None:
        raise ValueError("execute-worker step returned None")

    return result
