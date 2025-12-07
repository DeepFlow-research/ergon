"""Inngest function handlers for H-ARCANE experiments."""

import mimetypes
from datetime import datetime
from pathlib import Path
from typing import TypeVar
from uuid import UUID

import inngest
from pydantic import BaseModel

from h_arcane.agents.sandbox import SandboxManager
from h_arcane.agents.sandbox_executor import set_sandbox_manager, upload_tools_to_sandbox
from h_arcane.agents.stakeholder import RubricStakeholder
from h_arcane.agents.toolkit import WorkerToolkit
from h_arcane.agents.worker import ReActWorker, WorkerExecutionOutput
from h_arcane.db.models import CriterionResult, Evaluation, Experiment, Resource, Run, RunStatus
from h_arcane.db.queries import queries
from h_arcane.evaluation.models import TaskEvaluationResult
from h_arcane.evaluation.task_evaluator import evaluate_task_run
from h_arcane.inngest.client import inngest_client
from h_arcane.schemas.staged_rubric_schema import StagedRubric


class ExecutionDoneEvent(BaseModel):
    """Event data for execution/done event."""

    run_id: str


class RunEvaluateResult(BaseModel):
    """Result from run_evaluate function."""

    run_id: str
    normalized_score: float
    questions_asked: int


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
    """
    run_id_str = str(ctx.event.data["run_id"])
    run_id = UUID(run_id_str)

    # Load state
    async def load_run():
        resp = _require_not_none(queries.runs.get(run_id), f"Run {run_id} not found")
        # Convert to dict for serialization (PydanticSerializer handles dict -> Run conversion)
        return resp.model_dump(mode="json")

    run_dict = await ctx.step.run(
        "load-run",
        load_run,
    )
    # Convert back to Run object
    run = Run(**run_dict)

    if not run.experiment_id:
        raise ValueError(f"Run {run_id} has no experiment_id")

    async def load_experiment():
        resp = _require_not_none(
            queries.experiments.get(run.experiment_id),
            f"Experiment {run.experiment_id} not found",
        )
        return resp.model_dump(mode="json")

    experiment_dict = await ctx.step.run(
        "load-experiment",
        load_experiment,
    )
    experiment = Experiment(**experiment_dict)

    # Load input resources (stored with experiment_id, not run_id)
    async def load_input_resources():
        resources = queries.resources.get_by_experiment(experiment.id)
        return [r.model_dump(mode="json") for r in resources]

    input_resources_dicts = await ctx.step.run(
        "load-input-resources",
        load_input_resources,
    )
    input_resources = [Resource(**r_dict) for r_dict in input_resources_dicts]

    # Mark executing
    async def mark_executing():
        return queries.runs.update(run_id, status=RunStatus.EXECUTING, started_at=datetime.utcnow())

    await ctx.step.run(
        "mark-executing",
        mark_executing,
    )

    # Create sandbox
    sandbox_manager = SandboxManager(run_id)

    async def create_sandbox():
        return sandbox_manager.create()

    await ctx.step.run("create-sandbox", create_sandbox)

    try:
        # Upload inputs to sandbox
        async def upload_inputs():
            return sandbox_manager.upload_inputs(input_resources)

        await ctx.step.run("upload-inputs", upload_inputs)

        # Upload tools to sandbox
        async def upload_tools():
            return upload_tools_to_sandbox(sandbox_manager)

        await ctx.step.run("upload-tools", upload_tools)

        # Set sandbox manager globally for execute_in_sandbox()
        async def set_sandbox_manager_fn():
            return set_sandbox_manager(sandbox_manager)

        await ctx.step.run("set-sandbox-manager", set_sandbox_manager_fn)

        # Create stakeholder
        ground_truth = StagedRubric(**experiment.ground_truth_rubric)

        stakeholder = RubricStakeholder(
            ground_truth_rubric=ground_truth,
            task_description=experiment.task_description,
        )

        # Create toolkit (handles message/action logging, uses sandbox)
        toolkit = WorkerToolkit(
            run_id=run_id,
            stakeholder=stakeholder,
            sandbox_manager=sandbox_manager,
            max_questions=run.max_questions,
        )

        # Execute (tools execute in sandbox)
        worker = ReActWorker(model=run.worker_model)

        async def execute_task():
            return await worker.execute(
                run_id=run_id,
                task_description=experiment.task_description,
                input_resources=input_resources,
                toolkit=toolkit,
            )

        execution_output = await ctx.step.run(
            "execute-task", execute_task, output_type=WorkerExecutionOutput
        )

        # Download all outputs from sandbox
        output_dir = Path(f"data/runs/{run_id}")
        output_dir.mkdir(parents=True, exist_ok=True)

        async def download_outputs():
            return await sandbox_manager.download_all_outputs(output_dir)

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
                    run_id=run_id,
                    name=Path(lp).name,
                    mime_type=get_mime_type(lp),
                    file_path=lp,
                    size_bytes=sb,
                )

            resource = await ctx.step.run(
                f"register-resource-{local_path}",
                register_resource,
                output_type=Resource,
            )
            output_resource_ids.append(str(resource.id))

        # Save output to run
        async def save_output():
            return queries.runs.update(
                run_id,
                output_text=execution_output.output_text,
                output_resource_ids=output_resource_ids,
                questions_asked=toolkit.questions_asked,
            )

        await ctx.step.run(
            "save-output",
            save_output,
        )

        # Invoke evaluation (keeps everything in one trace)
        evaluation_result: RunEvaluateResult = await ctx.step.invoke(
            step_id="run-evaluate",
            function=run_evaluate,
            data=ExecutionDoneEvent(run_id=str(run_id)).model_dump(),
        )

    except Exception as exc:
        # Mark as failed
        error_msg = str(exc)

        async def mark_failed():
            return queries.runs.update(
                run_id,
                status=RunStatus.FAILED,
                error_message=error_msg,
            )

        await ctx.step.run(
            "mark-failed",
            mark_failed,
        )
        raise

    finally:
        # Always terminate sandbox
        async def terminate_sandbox():
            return sandbox_manager.terminate()

        await ctx.step.run("terminate-sandbox", terminate_sandbox)

    return {
        "run_id": str(run_id),
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
        return queries.runs.update(run_id, status=RunStatus.EVALUATING)

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

    # Evaluate task run
    async def evaluate_task():
        return await evaluate_task_run(
            run_id=run_id,
            task_input=experiment.task_description,
            agent_reasoning=run.output_text or "",
            agent_outputs=agent_outputs,
            rubric=ground_truth,
            sandbox_manager=None,  # Create temporary sandbox for code rules if needed
        )

    evaluation_result = await ctx.step.run(
        "evaluate-task-run", evaluate_task, output_type=TaskEvaluationResult
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

    # Store complete task evaluation result snapshot
    async def store_task_evaluation_result():
        return queries.task_evaluation_results.create(
            run_id=run_id,
            criterion_results=evaluation_result.criterion_results,
            total_score=evaluation_result.total_score,
            max_score=evaluation_result.max_score,
            normalized_score=evaluation_result.normalized_score,
            stages_evaluated=evaluation_result.stages_evaluated,
            stages_passed=evaluation_result.stages_passed,
            failed_gate=evaluation_result.failed_gate,
        )

    await ctx.step.run(
        "store-task-evaluation-result",
        store_task_evaluation_result,
        output_type=TaskEvaluationResult,
    )

    # Mark complete
    async def complete_run():
        return queries.runs.update(
            run_id,
            status=RunStatus.COMPLETED,
            completed_at=datetime.utcnow(),
            final_score=evaluation_result.total_score,
            normalized_score=evaluation_result.normalized_score,
        )

    await ctx.step.run(
        "complete-run",
        complete_run,
    )

    return RunEvaluateResult(
        run_id=str(run_id),
        normalized_score=evaluation_result.normalized_score,
        questions_asked=run.questions_asked or 0,
    )
