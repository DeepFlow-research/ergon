"""Worker execution child function.

Executes the worker agent in the sandbox using SDK types.
"""

import inngest
from inngest_agents import set_step

from h_arcane.benchmarks.enums import BenchmarkName
from h_arcane.benchmarks.registry import (
    get_sandbox_manager,
    get_stakeholder_factory,
    get_toolkit_factory,
    get_skills_dir,
)
from h_arcane.core._internal.agents.base import BaseStakeholder, BaseToolkit
from h_arcane.core._internal.db.models import AgentConfig
from h_arcane.core._internal.db.queries import queries
from h_arcane.core._internal.infrastructure.inngest_client import inngest_client
from h_arcane.core._internal.task.requests import WorkerExecuteRequest
from h_arcane.core._internal.task.results import WorkerExecuteResult
from h_arcane.core._internal.task.worker_context import get_worker
from h_arcane.core._internal.task.conversions import db_resources_to_sdk
from h_arcane.core._internal.task.schema import parse_task_tree
from h_arcane.core._internal.utils import require_not_none
from h_arcane.core.worker import WorkerContext, WorkerResult
from h_arcane.core.task import Task


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

    # Create/get sandbox for task (keyed by task_id)
    async def setup_sandbox() -> str:
        """Create sandbox for task and upload inputs."""
        skills_dir = get_skills_dir(benchmark_name)
        sandbox_id = await sandbox_manager.create(task_id, skills_dir=skills_dir)
        await sandbox_manager.upload_inputs(task_id, input_resources)
        return sandbox_id

    await ctx.step.run("setup-sandbox", setup_sandbox, output_type=str)

    # Create worker agent config (DB write, needs step)
    async def create_worker_config() -> AgentConfig:
        worker = get_worker(task_id)
        return queries.agent_configs.create(
            AgentConfig(
                run_id=run_id,
                name=worker.name,
                agent_type="react_worker",
                model=worker.model,
                system_prompt=worker.system_prompt,
                tools=[t.name if hasattr(t, "name") else str(t) for t in worker.tools],
            )
        )

    agent_config = await ctx.step.run(
        "create-worker-config", create_worker_config, output_type=AgentConfig
    )
    if agent_config is None:
        raise ValueError("Failed to create worker agent config")

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

    # Set step context for durable tools
    set_step(ctx.step)

    # Get worker from context (stored during execute_task)
    worker = get_worker(task_id)

    async def execute() -> WorkerExecuteResult:
        try:
            # Build SDK WorkerContext with toolkit for workers that need it
            sdk_resources = db_resources_to_sdk(input_resources)
            sandbox = sandbox_manager.get_sandbox(task_id)

            context = WorkerContext(
                task_id=task_id,
                run_id=run_id,
                sandbox=sandbox,
                input_resources=sdk_resources,
                toolkit=toolkit,  # Workers can self-configure from context
                agent_config_id=agent_config.id,
                metadata={
                    "benchmark_name": benchmark_name.value,
                    "experiment_id": str(experiment.id),
                },
            )

            # Get task name from task tree (if available)
            task_name = f"task_{task_id}"
            if experiment.task_tree:
                tree = parse_task_tree(experiment.task_tree)
                if tree:
                    task_node = tree.find_by_id(str(task_id))
                    if task_node:
                        task_name = task_node.name

            # Build SDK Task
            task = Task(
                id=task_id,
                name=task_name,
                description=payload.task_description,
                assigned_to=worker,
                resources=sdk_resources,
            )

            # Call worker with SDK types
            result: WorkerResult = await worker.execute(task, context)

            # Persist actions with run_id/agent_id
            for action in result.actions:
                action.run_id = run_id
                action.agent_id = agent_config.id
                queries.actions.create(action)

            # Persist Q&A exchanges (via communication service if needed)
            # Q&A is already persisted by toolkit during execution, but we could
            # add additional persistence here if needed

            return WorkerExecuteResult(
                success=result.success,
                output_text=result.output_text,
                questions_asked=toolkit.questions_asked
                if hasattr(toolkit, "questions_asked")
                else 0,
                error=result.error,
            )
        except Exception as e:
            return WorkerExecuteResult(
                success=False,
                error=str(e),
                questions_asked=toolkit.questions_asked
                if hasattr(toolkit, "questions_asked")
                else 0,
            )

    result = await ctx.step.run("execute-worker", execute, output_type=WorkerExecuteResult)
    if result is None:
        raise ValueError("execute-worker step returned None")

    return result
