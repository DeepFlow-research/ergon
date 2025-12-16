"""Inngest function handlers for H-ARCANE experiments."""

import mimetypes
from datetime import datetime
from pathlib import Path
from typing import TypeVar
from uuid import UUID, uuid4

import inngest

from h_arcane.agents.sandbox import SandboxManager
from h_arcane.agents.sandbox_executor import set_sandbox_manager, upload_tools_to_sandbox
from h_arcane.agents.worker import ReActWorker, WorkerExecutionOutput
from h_arcane.benchmarks.base import BaseStakeholder, BaseToolkit
from h_arcane.benchmarks.gdpeval.stakeholder import RubricStakeholder
from h_arcane.benchmarks.gdpeval.toolkit import GDPEvalToolkit
from h_arcane.benchmarks.minif2f.stakeholder import MiniF2FStakeholder
from h_arcane.benchmarks.minif2f.toolkit import MiniF2FToolkit
from h_arcane.schemas.base import BenchmarkName
from h_arcane.db.models import (
    AgentConfig,
    CriterionResult,
    Evaluation,
    Experiment,
    Resource,
    Run,
    RunStatus,
    TaskEvaluationResult,
)
from h_arcane.db.queries import queries
from h_arcane.evaluation.task_evaluator import evaluate_task_run
from h_arcane.inngest.client import inngest_client
from h_arcane.inngest.events import (
    ExecutionDoneEvent,
    RunCleanupEvent,
    RunEvaluateResult,
    TaskEvaluationEvent,
)
from h_arcane.evaluation.rubric import StagedRubric
from h_arcane.benchmarks.registry import get_worker_config


def get_mime_type(file_path: Path | str) -> str:
    """Get MIME type for a file."""
    mime_type, _ = mimetypes.guess_type(str(file_path))
    return mime_type or "application/octet-stream"


T = TypeVar("T")


def _require_not_none(value: T | None, error_msg: str) -> T:
    """Helper to raise error if value is None."""
    if value is None:
        raise ValueError(error_msg)
    return value


@inngest_client.create_function(  # type: ignore[misc]
    fn_id="worker-execute",
    trigger=inngest.TriggerEvent(event="run/start"),
    retries=2,
    concurrency=[inngest.Concurrency(limit=15, scope="fn")],
)
async def worker_execute(
    ctx: inngest.Context,
) -> dict:
    """
    Execute task with ReAct worker.

    Messages and actions are logged by WorkerToolkit during execution.
    All GDPEval tools execute inside E2B sandbox.

    Event data must contain:
    - `experiment_id`: UUID of experiment
    - `worker_model`: Optional, defaults to "gpt-4o"
    - `max_questions`: Optional, defaults to 10
    """
    event_data = ctx.event.data

    if "experiment_id" not in event_data:
        raise ValueError("Event data must contain 'experiment_id'")

    experiment_id = UUID(str(event_data["experiment_id"]))

    # Create run record
    async def create_run():
        # Extract and validate event data with proper types
        worker_model = event_data.get("worker_model", "gpt-4o")
        if not isinstance(worker_model, str):
            worker_model = "gpt-4o"

        max_questions = event_data.get("max_questions", 10)
        if not isinstance(max_questions, int):
            max_questions = 10

        run = queries.runs.create(
            Run(
                id=uuid4(),  # Use generated UUID
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
    # Use experiment_dict["id"] instead of experiment.id to avoid serialization issues
    async def load_input_resources():
        exp_id = UUID(experiment_dict["id"])  # Get ID from serialized dict
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
    # Extract resources from result dict
    input_resources_dicts = input_resources_result.get("resources", [])
    input_resources = [Resource(**r_dict) for r_dict in input_resources_dicts]

    # Mark executing
    async def mark_executing():
        existing = queries.runs.get(run.id)
        if existing:
            updated = existing.model_copy(
                update={
                    "status": RunStatus.EXECUTING,
                    "started_at": datetime.utcnow(),
                }
            )
            queries.runs.update(updated)
        # Return updated run status for visibility
        updated_run = queries.runs.get(run.id)
        if updated_run:
            return updated_run.model_dump(mode="json")
        return {"status": "executing", "run_id": str(run.id)}

    await ctx.step.run(
        "mark-executing",
        mark_executing,
    )

    try:
        # Create sandbox - idempotent: checks registry, creates only if needed
        # SandboxManager() is a singleton, so we can call it directly
        # Set timeout to 30 minutes to handle long-running agent executions
        async def create_sandbox():
            await SandboxManager().create(run.id, timeout_minutes=30)
            sandbox = SandboxManager().get_sandbox(run.id)
            return {
                "success": True,
                "run_id": str(run.id),
                "sandbox_created": sandbox is not None,
            }

        await ctx.step.run("create-sandbox", create_sandbox)

        # Upload inputs to sandbox
        async def upload_inputs():
            await SandboxManager().upload_inputs(run.id, input_resources)
            return {
                "success": True,
                "run_id": str(run.id),
                "files_uploaded": [r.name for r in input_resources],
                "count": len(input_resources),
            }

        await ctx.step.run("upload-inputs", upload_inputs)

        # Upload tools to sandbox
        async def upload_tools():
            await upload_tools_to_sandbox(SandboxManager(), run.id)
            # Get list of uploaded tools (same path logic as sandbox_executor)
            # functions.py is at h_arcane/inngest/functions.py, so parent.parent = h_arcane/
            tools_dir = Path(__file__).parent.parent / "tools"
            tool_files = []
            if tools_dir.exists():
                tool_files = [
                    f.name
                    for f in tools_dir.glob("*.py")
                    if f.name not in ("__init__.py", "responses.py")
                ]
            return {
                "success": True,
                "run_id": str(run.id),
                "tools_uploaded": tool_files,
                "count": len(tool_files),
            }

        await ctx.step.run("upload-tools", upload_tools)

        # Set sandbox manager globally for execute_in_sandbox()
        async def set_sandbox_manager_fn():
            set_sandbox_manager(SandboxManager(), run.id)
            return {
                "success": True,
                "run_id": str(run.id),
                "sandbox_manager_set": True,
            }

        await ctx.step.run("set-sandbox-manager", set_sandbox_manager_fn)

        # Create benchmark-specific stakeholder and toolkit
        # NOTE: benchmark_name may come through as a raw string depending on serialization paths
        # (e.g. Inngest/SQLModel). Normalize to our enum for comparisons.
        benchmark_name = (
            BenchmarkName(experiment.benchmark_name)
            if isinstance(experiment.benchmark_name, str)
            else experiment.benchmark_name
        )
        stakeholder: BaseStakeholder
        toolkit: BaseToolkit

        if benchmark_name == BenchmarkName.GDPEVAL:
            # GDPEval uses StagedRubric
            ground_truth = StagedRubric(**experiment.ground_truth_rubric)
            stakeholder = RubricStakeholder(
                ground_truth_rubric=ground_truth,
                task_description=experiment.task_description,
            )
            toolkit = GDPEvalToolkit(
                run_id=run.id,
                stakeholder=stakeholder,
                sandbox_manager=SandboxManager(),
                max_questions=run.max_questions,
            )
            stakeholder_prompt = RubricStakeholder.ANSWER_PROMPT
        elif benchmark_name == BenchmarkName.MINIF2F:
            # MiniF2F uses ground truth proof for hints
            ground_truth_proof = experiment.benchmark_specific_data.get("ground_truth_proof", "")
            stakeholder = MiniF2FStakeholder(
                ground_truth_proof=ground_truth_proof,
                problem_statement=experiment.task_description,
            )
            toolkit = MiniF2FToolkit(
                run_id=run.id,
                stakeholder=stakeholder,
                sandbox_manager=SandboxManager(),
                max_questions=run.max_questions,
            )
            stakeholder_prompt = MiniF2FStakeholder.HINT_PROMPT
        else:
            raise ValueError(f"Unsupported benchmark: {benchmark_name}")

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
                    system_prompt=stakeholder_prompt,
                    tools=[],  # Stakeholder doesn't use tools, just answers questions
                )
            )

        # Create agent config record for stakeholder
        await ctx.step.run(
            "create-stakeholder-agent-config",
            create_stakeholder_agent_config,
            output_type=AgentConfig,
        )

        # Execute (tools execute in sandbox)
        worker_config = get_worker_config(experiment.benchmark_name)
        worker = ReActWorker(model=run.worker_model, config=worker_config)

        async def execute_task():
            return await worker.execute(
                run_id=run.id,
                task_description=experiment.task_description,
                input_resources=input_resources,
                toolkit=toolkit,
            )

        execution_output = await ctx.step.run(
            "execute-task", execute_task, output_type=WorkerExecutionOutput
        )

        # Download all outputs from sandbox
        output_dir = Path(f"data/runs/{run.id}")
        output_dir.mkdir(parents=True, exist_ok=True)

        async def download_outputs():
            # Check if sandbox exists - if not, check if files were already downloaded
            sandbox_manager = SandboxManager()
            sandbox = sandbox_manager.get_sandbox(run.id)

            if not sandbox:
                # Sandbox doesn't exist (might have been terminated on retry)
                # Check if outputs were already downloaded
                if output_dir.exists() and any(output_dir.iterdir()):
                    # Files already exist, return them
                    downloaded = []
                    for file_path in output_dir.iterdir():
                        if file_path.is_file():
                            downloaded.append(
                                {
                                    "sandbox_path": f"/workspace/{file_path.name}",
                                    "local_path": str(file_path),
                                    "size_bytes": file_path.stat().st_size,
                                }
                            )
                    return downloaded
                else:
                    # No sandbox and no files - this is an error
                    raise RuntimeError(
                        f"Sandbox not available for run_id={run.id} and no previously downloaded files found. "
                        f"This may indicate the sandbox was terminated before outputs could be downloaded."
                    )

            # Sandbox exists, download files
            return await sandbox_manager.download_all_outputs(run.id, output_dir)

        downloaded_files: list[dict[str, str | int]] = await ctx.step.run(
            "download-outputs",
            download_outputs,
        )

        # Register downloaded files as Resources
        output_resource_ids = []
        for file_info in downloaded_files:
            local_path = str(file_info["local_path"])
            size_bytes = int(file_info["size_bytes"])

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

        # Save output to run
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

        # Invoke evaluation function (separate Inngest function)
        # Use step.invoke() to call another Inngest function
        evaluation_result: RunEvaluateResult = await ctx.step.invoke(
            step_id="run-evaluate",
            function=run_evaluate,
            data=ExecutionDoneEvent(run_id=str(run.id)).model_dump(),
        )

        # Emit cleanup event for successful completion
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
        # Mark as failed and emit cleanup event
        error_msg = str(exc)

        async def mark_failed():
            existing = queries.runs.get(run.id)
            if existing:
                updated = existing.model_copy(
                    update={
                        "status": RunStatus.FAILED,
                        "error_message": error_msg,
                    }
                )
                queries.runs.update(updated)
            return None

        await ctx.step.run(
            "mark-failed",
            mark_failed,
        )

        # Emit cleanup event for failure
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
        raise  # Best effort cleanup

    return {
        "run_id": str(run.id),
        "questions_asked": toolkit.questions_asked,
        "evaluation": evaluation_result.model_dump(),
    }


@inngest_client.create_function(  # type: ignore[misc]
    fn_id="run-evaluate",
    trigger=inngest.TriggerEvent(event="execution/done"),
    retries=1,
    output_type=RunEvaluateResult,
    concurrency=[inngest.Concurrency(limit=25, scope="fn")],
)
async def run_evaluate(
    ctx: inngest.Context,
) -> RunEvaluateResult:
    """
    Evaluate execution against ground truth rubric.

    Delegates to evaluate_task_run which orchestrates criterion evaluation.
    """
    run_id_str = str(ctx.event.data["run_id"])
    run_id = UUID(run_id_str)

    # Mark evaluating
    async def mark_evaluating():
        existing = queries.runs.get(run_id)
        if existing:
            updated = existing.model_copy(update={"status": RunStatus.EVALUATING})
            queries.runs.update(updated)
        return None

    await ctx.step.run("mark-evaluating", mark_evaluating)

    # Load state
    async def load_run_eval():
        resp = _require_not_none(queries.runs.get(run_id), f"Run {run_id} not found")
        # Convert to dict for serialization (PydanticSerializer handles dict -> Run conversion)
        return resp.model_dump(mode="json")

    run_dict = await ctx.step.run(
        "load-run",
        load_run_eval,
    )
    # Convert back to Run object
    run = Run(**run_dict)

    if not run.experiment_id:
        raise ValueError(f"Run {run_id} has no experiment_id")

    async def load_experiment_eval():
        resp = _require_not_none(
            queries.experiments.get(run.experiment_id),
            f"Experiment {run.experiment_id} not found",
        )
        return resp.model_dump(mode="json")

    experiment_dict = await ctx.step.run(
        "load-experiment",
        load_experiment_eval,
    )
    experiment = Experiment(**experiment_dict)

    # Load output resources
    async def load_resources():
        resources = queries.resources.get_all(run_id=run_id)
        return [r.model_dump(mode="json") for r in resources]

    all_resources_dicts = await ctx.step.run(
        "load-resources",
        load_resources,
    )
    all_resources = [Resource(**r_dict) for r_dict in all_resources_dicts]
    agent_outputs = [r for r in all_resources if str(r.id) in (run.output_resource_ids or [])]

    # Load rubric
    ground_truth = StagedRubric(**experiment.ground_truth_rubric)

    # Invoke evaluation function (runs criteria evaluations in parallel)
    evaluation_result: TaskEvaluationResult = await ctx.step.invoke(
        step_id="evaluate-task-run",
        function=evaluate_task_run,
        data=TaskEvaluationEvent(
            run_id=str(run_id),
            task_input=experiment.task_description,
            agent_reasoning=run.output_text or "",
            agent_outputs=[r.model_dump(mode="json") for r in agent_outputs],
            rubric=ground_truth.model_dump(mode="json"),
        ).model_dump(mode="json"),
    )

    # Save criterion results to DB
    # criterion_results are now dicts, convert back to CriterionResult objects
    for cr_dict in evaluation_result.criterion_results:
        # Remove id and run_id from dict if present (we'll set run_id explicitly)
        cr_dict_clean = {k: v for k, v in cr_dict.items() if k not in ("id", "run_id")}
        cr_obj = CriterionResult(**cr_dict_clean, run_id=run_id)

        async def store_criterion(criterion_result=cr_obj):
            return queries.criterion_results.create_from_eval(
                run_id=run_id, eval_result=criterion_result
            )

        await ctx.step.run(
            f"store-criterion-{cr_obj.stage_num}-{cr_obj.criterion_num}",
            store_criterion,
            output_type=CriterionResult,
        )

    # Store aggregate evaluation
    async def store_evaluation():
        eval_instance = Evaluation(
            run_id=run_id,
            total_score=evaluation_result.total_score,
            max_score=evaluation_result.max_score,
            normalized_score=evaluation_result.normalized_score,
            stages_evaluated=evaluation_result.stages_evaluated,
            stages_passed=evaluation_result.stages_passed,
            failed_gate=evaluation_result.failed_gate,
        )
        return queries.evaluations.create_from_eval(
            run_id=run_id,
            eval_result=eval_instance,
        )

    await ctx.step.run(
        "store-evaluation",
        store_evaluation,
        output_type=Evaluation,
    )

    # Store complete task evaluation result snapshot (idempotent)
    async def store_task_evaluation_result():
        # Check if already exists
        existing = queries.task_evaluation_results.get_by_run(run_id)

        if existing:
            # Update existing record
            updated = existing.model_copy(
                update={
                    "criterion_results": evaluation_result.criterion_results,
                    "total_score": evaluation_result.total_score,
                    "max_score": evaluation_result.max_score,
                    "normalized_score": evaluation_result.normalized_score,
                    "stages_evaluated": evaluation_result.stages_evaluated,
                    "stages_passed": evaluation_result.stages_passed,
                    "failed_gate": evaluation_result.failed_gate,
                }
            )
            return queries.task_evaluation_results.update(updated)
        else:
            # Create new record
            return queries.task_evaluation_results.create(
                TaskEvaluationResult(
                    run_id=run_id,
                    criterion_results=evaluation_result.criterion_results,
                    total_score=evaluation_result.total_score,
                    max_score=evaluation_result.max_score,
                    normalized_score=evaluation_result.normalized_score,
                    stages_evaluated=evaluation_result.stages_evaluated,
                    stages_passed=evaluation_result.stages_passed,
                    failed_gate=evaluation_result.failed_gate,
                )
            )

    await ctx.step.run(
        "store-task-evaluation-result",
        store_task_evaluation_result,
        output_type=TaskEvaluationResult,
    )

    # Mark complete
    async def complete_run():
        existing = queries.runs.get(run_id)
        if existing:
            updated = existing.model_copy(
                update={
                    "status": RunStatus.COMPLETED,
                    "completed_at": datetime.utcnow(),
                    "final_score": evaluation_result.total_score,
                    "normalized_score": evaluation_result.normalized_score,
                    "questions_asked": run.questions_asked or 0,
                }
            )
            queries.runs.update(updated)
        return None

    await ctx.step.run(
        "complete-run",
        complete_run,
    )

    return RunEvaluateResult(
        run_id=str(run_id),
        normalized_score=evaluation_result.normalized_score,
        questions_asked=run.questions_asked or 0,
    )


@inngest_client.create_function(  # type: ignore[misc]
    fn_id="run-cleanup",
    trigger=inngest.TriggerEvent(event="run/cleanup"),
    retries=2,  # Retry cleanup if it fails
    concurrency=[inngest.Concurrency(limit=50, scope="fn")],
)
async def run_cleanup(
    ctx: inngest.Context,
) -> dict:
    """
    Cleanup function for completed or failed runs.

    Handles:
    - Terminating sandbox for the run_id
    - Ensuring run status is correctly set (idempotent)
    - Logging cleanup results
    """
    # Parse event data
    event_data_dict = ctx.event.data
    run_id_str = str(event_data_dict.get("run_id", ""))
    status_str = str(event_data_dict.get("status", "failed"))
    error_message = (
        str(event_data_dict.get("error_message", ""))
        if event_data_dict.get("error_message")
        else None
    )

    run_id = UUID(run_id_str)
    status = status_str

    # Terminate sandbox (idempotent - safe to call multiple times)
    async def terminate_sandbox():
        try:
            await SandboxManager().terminate(run_id)
            return {
                "success": True,
                "run_id": str(run_id),
                "sandbox_terminated": True,
            }
        except Exception as e:
            # Log but don't fail - sandbox might already be terminated
            error_str = str(e)
            if "not created" in error_str.lower() or "not found" in error_str.lower():
                # Sandbox already terminated or never existed - this is fine
                return {
                    "success": True,
                    "run_id": str(run_id),
                    "sandbox_terminated": False,
                    "message": "Sandbox already terminated or never existed",
                }
            # Other error - log but continue
            print(f"Warning: Error terminating sandbox for run_id={run_id}: {e}")
            return {
                "success": False,
                "run_id": str(run_id),
                "error": error_str,
            }

    terminate_result = await ctx.step.run("terminate-sandbox", terminate_sandbox)

    # Verify run status is set correctly (idempotent check)
    async def verify_run_status():
        run = queries.runs.get(run_id)
        if not run:
            return {"error": f"Run {run_id} not found"}

        expected_status = RunStatus.COMPLETED if status == "completed" else RunStatus.FAILED
        if run.status != expected_status:
            # Update status if it doesn't match (shouldn't happen, but be safe)
            updated = run.model_copy(
                update={
                    "status": expected_status,
                    "error_message": error_message if status == "failed" else None,
                }
            )
            queries.runs.update(updated)
            return {
                "status_updated": True,
                "old_status": run.status.value,
                "new_status": expected_status.value,
            }
        return {
            "status_verified": True,
            "status": run.status.value,
        }

    status_result = await ctx.step.run("verify-run-status", verify_run_status)

    return {
        "run_id": str(run_id),
        "status": status,
        "sandbox_cleanup": terminate_result,
        "status_verification": status_result,
    }
