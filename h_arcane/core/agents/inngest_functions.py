"""Inngest functions for the agents domain.

These functions handle agent task execution:
- worker_execute: Execute a task with the ReAct worker
"""

import mimetypes
from datetime import datetime, timezone
from pathlib import Path
from typing import TypeVar
from uuid import UUID, uuid4

import inngest
from inngest_agents import set_step

from h_arcane.benchmarks.common.workers import ReActWorker
from h_arcane.benchmarks.enums import BenchmarkName
from h_arcane.benchmarks.registry import (
    get_sandbox_manager,
    get_skills_dir,
    get_stakeholder_factory,
    get_toolkit_factory,
    get_worker_config,
)
from h_arcane.core.agents.base import BaseStakeholder, BaseToolkit
from h_arcane.core.agents.events import ExecutionDoneEvent
from h_arcane.core.db.models import (
    AgentConfig,
    Experiment,
    Resource,
    Run,
    RunStatus,
)
from h_arcane.core.db.queries import queries
from h_arcane.core.evaluation.events import RunEvaluateResult
from h_arcane.core.infrastructure.events import RunCleanupEvent
from h_arcane.core.infrastructure.inngest_client import inngest_client
from h_arcane.core.infrastructure.sandbox import DownloadedFiles
from h_arcane.settings import settings

# Register markdown MIME type so .md files get proper typing
mimetypes.add_type("text/markdown", ".md")

T = TypeVar("T")


def get_mime_type(file_path: Path | str) -> str:
    """Get MIME type for a file."""
    mime_type, _ = mimetypes.guess_type(str(file_path))
    return mime_type or "application/octet-stream"


def _require_not_none(value: T | None, error_msg: str) -> T:
    """Helper to raise error if value is None."""
    if value is None:
        raise ValueError(error_msg)
    return value


@inngest_client.create_function(
    fn_id="worker-execute",
    trigger=inngest.TriggerEvent(event="run/start"),
    retries=0,
    concurrency=[inngest.Concurrency(limit=15, scope="fn")],
)
async def worker_execute(
    ctx: inngest.Context,
) -> dict:
    """
    Execute task with ReAct worker.

    Messages and actions are logged by WorkerToolkit during execution.
    All tools execute inside E2B sandbox via skills architecture.

    Event data must contain:
    - `experiment_id`: UUID of experiment
    - `worker_model`: Optional, defaults to "gpt-4o"
    - `max_questions`: Optional, defaults to 10
    """
    # Import here to avoid circular dependency
    from h_arcane.core.evaluation.inngest_functions import run_evaluate

    event_data = ctx.event.data

    if "experiment_id" not in event_data:
        raise ValueError("Event data must contain 'experiment_id'")

    experiment_id = UUID(str(event_data["experiment_id"]))

    # Create run record
    async def create_run():
        worker_model = event_data.get("worker_model", "gpt-4o")
        if not isinstance(worker_model, str):
            worker_model = "gpt-4o"

        max_questions = event_data.get("max_questions", 10)
        if not isinstance(max_questions, int):
            max_questions = 10

        run = queries.runs.create(
            Run(
                id=uuid4(),
                experiment_id=experiment_id,
                worker_model=worker_model,
                max_questions=max_questions,
            )
        )
        return run.model_dump(mode="json")

    run_dict = await ctx.step.run("create-run", create_run)
    run = Run(**run_dict)

    async def load_experiment():
        resp = _require_not_none(
            queries.experiments.get(experiment_id),
            f"Experiment {experiment_id} not found",
        )
        return resp.model_dump(mode="json")

    experiment_dict = await ctx.step.run(
        "load-experiment",
        load_experiment,
    )
    experiment = Experiment(**experiment_dict)

    # Load input resources (stored with experiment_id, not run_id)
    async def load_input_resources():
        exp_id = UUID(experiment_dict["id"])
        resources = queries.resources.get_by_experiment(exp_id)
        resource_dicts = [r.model_dump(mode="json") for r in resources]
        return {
            "resources": resource_dicts,
            "count": len(resource_dicts),
            "experiment_id": str(exp_id),
        }

    input_resources_result = await ctx.step.run(
        "load-input-resources",
        load_input_resources,
    )
    input_resources_dicts = input_resources_result.get("resources", [])
    input_resources = [Resource(**r_dict) for r_dict in input_resources_dicts]

    # Mark executing
    async def mark_executing():
        existing = queries.runs.get(run.id)
        if existing:
            updated = existing.model_copy(
                update={
                    "status": RunStatus.EXECUTING,
                    "started_at": datetime.now(timezone.utc),
                }
            )
            queries.runs.update(updated)
        updated_run = queries.runs.get(run.id)
        if updated_run:
            return updated_run.model_dump(mode="json")
        return {"status": "executing", "run_id": str(run.id)}

    await ctx.step.run(
        "mark-executing",
        mark_executing,
    )

    # Set step context for durable tools (before any tool execution)
    set_step(ctx.step)

    try:
        benchmark_name = (
            BenchmarkName(experiment.benchmark_name)
            if isinstance(experiment.benchmark_name, str)
            else experiment.benchmark_name
        )

        skills_dir = get_skills_dir(benchmark_name)

        # === COMPOSITION ROOT: lookup factories from registry ===
        stakeholder_factory = get_stakeholder_factory(benchmark_name)
        toolkit_factory = get_toolkit_factory(benchmark_name)

        sandbox_manager = get_sandbox_manager(benchmark_name)
        stakeholder: BaseStakeholder = stakeholder_factory(experiment)
        toolkit: BaseToolkit = toolkit_factory(
            run.id, experiment.id, stakeholder, sandbox_manager, run.max_questions
        )

        async def create_stakeholder_agent_config():
            stakeholder_display_name = (
                benchmark_name.value.title()
                if isinstance(benchmark_name, BenchmarkName)
                else str(benchmark_name).title()
            )
            return queries.agent_configs.create(
                AgentConfig(
                    run_id=run.id,
                    name=f"{stakeholder_display_name} Stakeholder",
                    agent_type="stakeholder",
                    model=stakeholder.model,
                    system_prompt=stakeholder.system_prompt,
                    tools=[],
                )
            )

        await ctx.step.run(
            "create-stakeholder-agent-config",
            create_stakeholder_agent_config,
            output_type=AgentConfig,
        )

        worker_config = get_worker_config(benchmark_name)
        worker = ReActWorker(model=run.worker_model, config=worker_config)

        output_dir = Path(f"data/runs/{run.id}")
        output_dir.mkdir(parents=True, exist_ok=True)

        sandbox_envs = {
            "EXA_API_KEY": settings.exa_api_key,
        }
        e2b_sandbox_id = await sandbox_manager.create(
            run.id, skills_dir=skills_dir, timeout_minutes=30, envs=sandbox_envs
        )

        async def save_sandbox_id():
            existing = queries.runs.get(run.id)
            if existing and not existing.e2b_sandbox_id:
                updated = existing.model_copy(update={"e2b_sandbox_id": e2b_sandbox_id})
                queries.runs.update(updated)
            return {"sandbox_id": e2b_sandbox_id}

        await ctx.step.run("save-sandbox-id", save_sandbox_id)

        await sandbox_manager.upload_inputs(run.id, input_resources)

        exec_out = await worker.execute(
            run_id=run.id,
            task_description=experiment.task_description,
            input_resources=input_resources,
            toolkit=toolkit,
        )

        async def download_outputs():
            downloaded_files = await sandbox_manager.download_all_outputs(run.id, output_dir)
            return downloaded_files

        downloaded_files = await ctx.step.run(
            "download-outputs", download_outputs, output_type=DownloadedFiles
        )
        execution_output = exec_out

        output_resource_ids = []
        for file_info in downloaded_files.files:
            local_path = file_info.local_path
            size_bytes = file_info.size_bytes

            async def register_resource(lp=local_path, sb=size_bytes):
                return queries.resources.create(
                    Resource(
                        run_id=run.id,
                        name=Path(lp).name,
                        mime_type=get_mime_type(lp),
                        file_path=lp,
                        size_bytes=sb,
                    )
                )

            resource = await ctx.step.run(
                f"register-resource-{local_path}",
                register_resource,
                output_type=Resource,
            )
            output_resource_ids.append(str(resource.id))

        async def save_output() -> Run | None:
            existing = queries.runs.get(run.id)
            if existing:
                updated = existing.model_copy(
                    update={
                        "output_text": execution_output.output_text,
                        "output_resource_ids": output_resource_ids,
                        "questions_asked": toolkit.questions_asked,
                    }
                )
                queries.runs.update(updated)
                return updated
            return None

        await ctx.step.run(
            "save-output",
            save_output,
            output_type=Run | None,
        )

        evaluation_result: RunEvaluateResult = await ctx.step.invoke(
            step_id="run-evaluate",
            function=run_evaluate,
            data=ExecutionDoneEvent(run_id=str(run.id)).model_dump(),
        )

        async def emit_cleanup_success():
            await inngest_client.send(
                inngest.Event(
                    name="run/cleanup",
                    data=RunCleanupEvent(
                        run_id=str(run.id),
                        status="completed",
                    ).model_dump(),
                )
            )
            return {"event_emitted": True}

        await ctx.step.run("emit-cleanup-success", emit_cleanup_success)

    except Exception as exc:
        error_msg = str(exc)

        async def mark_failed() -> str:
            existing = queries.runs.get(run.id)
            if existing:
                updated = existing.model_copy(
                    update={
                        "status": RunStatus.FAILED,
                        "error_message": error_msg,
                    }
                )
                queries.runs.update(updated)
            return f"Error message: {error_msg}"

        await ctx.step.run(
            "mark-failed",
            mark_failed,
        )

        async def emit_cleanup_failure():
            await inngest_client.send(
                inngest.Event(
                    name="run/cleanup",
                    data=RunCleanupEvent(
                        run_id=str(run.id),
                        status="failed",
                        error_message=error_msg,
                    ).model_dump(),
                )
            )
            return {"event_emitted": True}

        await ctx.step.run("emit-cleanup-failure", emit_cleanup_failure)

        raise inngest.NonRetriableError(f"Worker execution failed: {error_msg}")

    return {
        "run_id": str(run.id),
        "questions_asked": toolkit.questions_asked,
        "evaluation": evaluation_result.model_dump(),
    }
