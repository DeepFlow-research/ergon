"""In-process deterministic harness for benchmark state tests."""

from __future__ import annotations

import json
from asyncio import gather
from collections import defaultdict, deque
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from h_arcane.benchmarks.enums import BenchmarkName
from h_arcane.benchmarks.minif2f.toolkit import MiniF2FToolkit
from h_arcane.benchmarks.researchrubrics.toolkit import ResearchRubricsToolkit
from h_arcane.benchmarks.registry import get_sandbox_manager, get_skills_dir
from h_arcane.core._internal.agents.base import BaseStakeholder
from h_arcane.core._internal.db.models import (
    Action,
    CriterionResult,
    ResourceRecord,
    TaskEvaluationResult,
)
from h_arcane.core._internal.db.queries import queries
from h_arcane.core._internal.evaluation.executors import CriterionExecutor
from h_arcane.core._internal.evaluation.schemas import CriterionContext, TaskEvaluationContext
from h_arcane.core._internal.evaluation.services import EvaluatorDispatchService, RubricEvaluationService
from h_arcane.core._internal.evaluation.services.dto import DispatchEvaluatorsCommand
from h_arcane.core._internal.infrastructure import tracing
from h_arcane.core._internal.infrastructure.sandbox import DownloadedFiles
from h_arcane.core._internal.task.inngest_functions.sandbox_setup import _create_sandbox
from h_arcane.core._internal.task.inngest_functions.worker_execute import (
    _execute_worker,
    _get_or_create_stakeholder_config,
    _get_or_create_worker_config,
    _link_execution_to_agent,
)
from h_arcane.core._internal.task.persistence import persist_agent_mapping, persist_workflow
from h_arcane.core._internal.task.services import (
    TaskExecutionService,
    TaskPropagationService,
    WorkflowFinalizationService,
    WorkflowInitializationService,
)
from h_arcane.core._internal.task.services.dto import (
    FailTaskExecutionCommand,
    FinalizeTaskExecutionCommand,
    FinalizeWorkflowCommand,
    InitializeWorkflowCommand,
    PrepareTaskExecutionCommand,
    PropagateTaskCompletionCommand,
)
from h_arcane.core._internal.task.worker_context import (
    clear_workers_from_task,
    store_workers_from_task,
)
from h_arcane.core._internal.task.validation import validate_task_dag
from h_arcane.core._internal.utils import get_mime_type, utcnow
from h_arcane.core._internal.agents.registry import AgentRegistry
from h_arcane.core._internal.infrastructure.tracing import (
    CompletedSpan,
    SpanEvent,
    TraceContext,
    get_trace_sink,
    override_trace_sink,
    persist_outputs_context,
    workflow_start_context,
    task_execute_context,
)
from h_arcane.core.settings import settings
from h_arcane.core.task import Task
from h_arcane.core.worker import WorkerContext, WorkerResult
from tests.deterministic.schemas import (
    DeterministicCase,
    DeterministicRunResult,
    RunTranscript,
    ScriptedJudgeResponse,
    TranscriptEventRecord,
    TranscriptSpanRecord,
)


async def _reset_e2b_async_transport() -> None:
    """Reset the E2B async transport singleton between test runs."""
    try:
        from e2b.api.client_async import AsyncTransportWithLogger

        transport = AsyncTransportWithLogger.singleton
        if transport is not None:
            await transport.aclose()
        AsyncTransportWithLogger.singleton = None
    except Exception:
        # Best-effort cleanup for SDK-global state in tests.
        return


def _serialize_output(value: Any) -> str:
    """Serialize a tool output for Action persistence."""
    if isinstance(value, BaseModel):
        return json.dumps(value.model_dump(), indent=2, default=str)
    if isinstance(value, str):
        return value
    return json.dumps(value, indent=2, default=str)


def _extract_error(value: Any) -> dict[str, Any] | None:
    """Extract Action.error-compatible payload from a tool response."""
    output_dict: dict[str, Any] | None = None
    if isinstance(value, BaseModel):
        output_dict = value.model_dump()
    elif isinstance(value, dict):
        output_dict = value

    if not output_dict:
        return None

    success = output_dict.get("success")
    error_message = output_dict.get("error")
    if success is False or (error_message and success is not True):
        return {
            "message": error_message or "Unknown error",
            "exception_type": output_dict.get("exception_type"),
            "stack_trace": output_dict.get("stack_trace"),
            "details": None,
        }
    return None


class CaptureTraceSink:
    """Trace sink that captures deterministic spans and events for assertions."""

    def __init__(self) -> None:
        self.spans: list[CompletedSpan] = []
        self.events: list[tuple[TraceContext, SpanEvent]] = []

    def emit_span(self, span: CompletedSpan) -> None:
        self.spans.append(span)

    def add_event(
        self,
        context: TraceContext,
        name: str,
        attributes: dict[str, Any] | None = None,
        timestamp: datetime | None = None,
    ) -> None:
        self.events.append(
            (
                context,
                SpanEvent(
                    name=name,
                    timestamp=timestamp or utcnow(),
                    attributes=attributes or {},
                ),
            )
        )

    def child_context(
        self,
        parent: TraceContext,
        *,
        span_key: str,
        run_id: UUID | None = None,
        task_id: UUID | None = None,
        execution_id: UUID | None = None,
        evaluator_id: UUID | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> TraceContext:
        return TraceContext(
            trace_id=parent.trace_id,
            span_id=tracing.span_id_from_key(parent.trace_id, span_key),
            parent_span_id=parent.span_id,
            run_id=run_id if run_id is not None else parent.run_id,
            task_id=task_id if task_id is not None else parent.task_id,
            execution_id=execution_id if execution_id is not None else parent.execution_id,
            evaluator_id=evaluator_id if evaluator_id is not None else parent.evaluator_id,
            attributes=attributes or {},
        )

    def to_transcript(self) -> RunTranscript:
        return RunTranscript(
            spans=[
                TranscriptSpanRecord(
                    span_name=span.name,
                    attributes={**span.context.attributes, **span.attributes},
                    status_code=span.status_code,
                    status_message=span.status_message,
                )
                for span in self.spans
            ],
            events=[
                TranscriptEventRecord(
                    span_name=context.run_id.hex if context.run_id else "unknown",
                    event_name=event.name,
                    attributes=event.attributes,
                    timestamp=event.timestamp,
                )
                for context, event in self.events
            ],
        )


@contextmanager
def capture_trace_sink() -> Any:
    """Install a process-local trace sink for deterministic tests."""
    sink = CaptureTraceSink()
    with override_trace_sink(sink):
        yield sink


@asynccontextmanager
async def deterministic_runtime_session():
    """Manage shared runtime state for one deterministic batch."""
    await _reset_e2b_async_transport()
    try:
        yield
    finally:
        await _reset_e2b_async_transport()


class ScriptedStakeholder(BaseStakeholder):
    """Deterministic stakeholder with queued responses."""

    def __init__(self, answers: list[str], label: str):
        self._answers = deque(answers)
        self._label = label

    @property
    def model(self) -> str:
        return "scripted-stakeholder"

    @property
    def system_prompt(self) -> str:
        return f"Deterministic stakeholder for {self._label}"

    async def answer(self, question: str, history: list[Any] | None = None) -> str:
        if self._answers:
            return self._answers.popleft()
        return f"[No scripted stakeholder answer configured for: {question}]"


class SandboxManagerProxy:
    """Delegate to the real sandbox manager while overriding selected skills."""

    def __init__(
        self,
        delegate: Any,
        scripted_skill_responses: list[Any],
    ) -> None:
        self._delegate = delegate
        self._responses: dict[str, deque[dict[str, Any]]] = defaultdict(deque)
        for sequence in scripted_skill_responses:
            self._responses[sequence.skill_name].extend(sequence.responses)

    async def create(self, *args: Any, **kwargs: Any) -> str:
        return await self._delegate.create(*args, **kwargs)

    async def upload_inputs(self, *args: Any, **kwargs: Any) -> None:
        await self._delegate.upload_inputs(*args, **kwargs)

    async def run_skill(
        self,
        task_id: UUID,
        skill_name: str,
        return_type: type[BaseModel],
        **kwargs: Any,
    ) -> BaseModel:
        if self._responses[skill_name]:
            payload = self._responses[skill_name].popleft()
            return return_type.model_validate(payload)
        return await self._delegate.run_skill(task_id, skill_name, return_type, **kwargs)

    async def download_all_outputs(self, task_id: UUID, output_dir: Path) -> DownloadedFiles:
        return await self._delegate.download_all_outputs(task_id, output_dir)

    async def terminate(self, task_id: UUID, reason: str = "completed") -> None:
        await self._delegate.terminate(task_id, reason=reason)

    async def reset_timeout(self, task_id: UUID, timeout_minutes: int = 30) -> bool:
        return await self._delegate.reset_timeout(task_id, timeout_minutes=timeout_minutes)

    def get_sandbox(self, task_id: UUID) -> Any:
        return self._delegate.get_sandbox(task_id)

    def register_created_file(self, task_id: UUID, sandbox_path: str) -> None:
        self._delegate.register_created_file(task_id, sandbox_path)

    def get_sandbox_path(self, task_id: UUID, local_path: str) -> str | None:
        return self._delegate.get_sandbox_path(task_id, local_path)


class HarnessCriterionRuntime:
    """Evaluation runtime that reuses the already-created task sandbox."""

    def __init__(
        self,
        *,
        run_id: UUID,
        task_id: UUID,
        sandbox_manager: SandboxManagerProxy,
        judge_responses: deque[ScriptedJudgeResponse],
    ) -> None:
        self.run_id = run_id
        self.task_id = task_id
        self.sandbox_manager = sandbox_manager
        self.judge_responses = judge_responses

    async def ensure_sandbox(self) -> None:
        if self.sandbox_manager.get_sandbox(self.task_id) is None:
            raise RuntimeError(f"Sandbox not available for task {self.task_id}")

    async def upload_files(self, files: list[ResourceRecord]) -> None:
        sandbox = self.sandbox_manager.get_sandbox(self.task_id)
        if sandbox is None:
            raise RuntimeError("Sandbox not created - call ensure_sandbox first")
        await sandbox.commands.run("mkdir -p /evaluation")
        for resource in files:
            await sandbox.files.write(f"/evaluation/{resource.name}", resource.load_content())

    async def write_file(self, path: str, content: bytes) -> None:
        sandbox = self.sandbox_manager.get_sandbox(self.task_id)
        if sandbox is None:
            raise RuntimeError("Sandbox not created - call ensure_sandbox first")
        await sandbox.files.write(path, content)

    async def run_command(self, command: str, timeout: int = 30) -> Any:
        sandbox = self.sandbox_manager.get_sandbox(self.task_id)
        if sandbox is None:
            raise RuntimeError("Sandbox not created - call ensure_sandbox first")
        result = await sandbox.commands.run(command, timeout=timeout)
        from h_arcane.core._internal.evaluation.schemas import CommandResult

        return CommandResult(stdout=result.stdout, stderr=result.stderr, exit_code=result.exit_code)

    async def execute_code(self, code: str) -> Any:
        sandbox = self.sandbox_manager.get_sandbox(self.task_id)
        if sandbox is None:
            raise RuntimeError("Sandbox not created")
        execution = await sandbox.run_code(code, language="python", timeout=30)
        from h_arcane.core._internal.evaluation.schemas import SandboxResult

        return SandboxResult(
            stdout=list(execution.logs.stdout),
            stderr=list(execution.logs.stderr),
        )

    async def call_llm_judge(self, messages: list[Any], response_type: type[BaseModel]) -> BaseModel:
        if not self.judge_responses:
            raise RuntimeError("No scripted judge response available")
        response = self.judge_responses.popleft()
        return response_type.model_validate(response.model_dump())

    async def cleanup(self) -> None:
        return None


class SequentialCriterionExecutor(CriterionExecutor):
    """Run rubric criteria in-process, one after another."""

    def __init__(
        self,
        *,
        run_id: UUID,
        task_id: UUID,
        sandbox_manager: SandboxManagerProxy,
        judge_responses: deque[ScriptedJudgeResponse],
    ) -> None:
        self.run_id = run_id
        self.task_id = task_id
        self.sandbox_manager = sandbox_manager
        self.judge_responses = judge_responses

    async def execute_all(
        self,
        task_context: TaskEvaluationContext,
        benchmark_name: str,
        criteria: list[Any],
    ) -> list[CriterionResult]:
        runtime = HarnessCriterionRuntime(
            run_id=self.run_id,
            task_id=self.task_id,
            sandbox_manager=self.sandbox_manager,
            judge_responses=self.judge_responses,
        )
        results: list[CriterionResult] = []
        for spec in criteria:
            context = CriterionContext(
                run_id=task_context.run_id,
                task_input=task_context.task_input,
                agent_reasoning=task_context.agent_reasoning,
                agent_outputs=task_context.agent_outputs,
                stage_idx=spec.stage_idx,
                stage_name=spec.stage_name,
                criterion_idx=spec.criterion_idx,
                max_score=spec.max_score,
            )
            results.append(await spec.criterion.evaluate(runtime, context))
        return results


class ScriptedWorker:
    """Deterministic worker that invokes real toolkit tools in a scripted order."""

    def __init__(self, case: DeterministicCase):
        self.case = case
        self.id = UUID("11111111-1111-1111-1111-111111111111")
        self.name = f"{case.name}_worker"
        self.model = "scripted-model"
        self.tools: list[Any] = []
        self.system_prompt = f"Deterministic scripted worker for {case.name}"

    async def execute(self, task: Task, context: WorkerContext) -> WorkerResult:
        toolkit = context.toolkit
        if toolkit is None:
            raise ValueError("ScriptedWorker requires toolkit in context.toolkit")

        tools = {tool.name: tool for tool in toolkit.get_tools()}
        self.tools = list(tools.values())
        actions: list[Action] = []

        for index, step in enumerate(self.case.scripted_steps):
            tool = tools.get(step.tool_name)
            if tool is None:
                raise ValueError(f"Tool {step.tool_name} not available for {self.case.name}")
            started_at = utcnow()
            output = await tool.on_invoke_tool(None, json.dumps(step.arguments))
            completed_at = utcnow()
            actions.append(
                Action(
                    run_id=context.run_id,
                    agent_id=context.agent_config_id,
                    action_num=index,
                    action_type=step.tool_name,
                    input=json.dumps(step.arguments, default=str),
                    output=_serialize_output(output),
                    error=_extract_error(output),
                    started_at=started_at,
                    completed_at=completed_at,
                    duration_ms=max(
                        1,
                        int((completed_at - started_at).total_seconds() * 1000),
                    ),
                    agent_total_tokens=0,
                    agent_total_cost_usd=0.0,
                )
            )

        return WorkerResult(
            success=True,
            output_text=self.case.final_output_text,
            reasoning=f"Deterministic execution for {self.case.name}",
            actions=actions,
            qa_exchanges=toolkit.get_qa_history(),
            outputs=[],
            error=None,
        )


def _build_toolkit(
    case: DeterministicCase,
    *,
    task_id: UUID,
    run_id: UUID,
    experiment_id: UUID,
    stakeholder: BaseStakeholder,
    sandbox_manager: SandboxManagerProxy,
) -> Any:
    if case.benchmark_name == "minif2f":
        return MiniF2FToolkit(
            task_id=task_id,
            run_id=run_id,
            experiment_id=experiment_id,
            stakeholder=stakeholder,
            sandbox_manager=sandbox_manager,
            max_questions=10,
        )
    return ResearchRubricsToolkit(
        task_id=task_id,
        run_id=run_id,
        experiment_id=experiment_id,
        stakeholder=stakeholder,
        sandbox_manager=sandbox_manager,
        max_questions=10,
    )


async def _persist_outputs(
    *,
    run_id: UUID,
    task_id: UUID,
    execution_id: UUID,
    output_dir: Path,
    sandbox_manager: SandboxManagerProxy,
    input_resource_ids: list[UUID],
) -> list[UUID]:
    downloaded = await sandbox_manager.download_all_outputs(task_id, output_dir)
    output_resource_ids: list[UUID] = []
    started_at = utcnow()
    for file_info in downloaded.files:
        resource = queries.resources.create(
            ResourceRecord(
                run_id=run_id,
                task_id=task_id,
                task_execution_id=execution_id,
                is_input=False,
                name=Path(file_info.local_path).name,
                mime_type=get_mime_type(file_info.local_path),
                file_path=file_info.local_path,
                size_bytes=file_info.size_bytes,
                source_resource_ids=[str(resource_id) for resource_id in input_resource_ids],
            )
        )
        output_resource_ids.append(resource.id)
    get_trace_sink().emit_span(
        CompletedSpan(
            name="persist.outputs",
            context=persist_outputs_context(
                run_id,
                task_id,
                execution_id,
            ),
            start_time=started_at,
            end_time=utcnow(),
            attributes={
                "outputs_count": len(output_resource_ids),
                "output_resource_ids": [str(resource_id) for resource_id in output_resource_ids],
            },
        )
    )
    return output_resource_ids


async def _run_evaluators(
    *,
    run_id: UUID,
    task_id: UUID,
    execution_id: UUID,
    experiment_id: UUID,
    sandbox_manager: SandboxManagerProxy,
    judge_responses: deque[ScriptedJudgeResponse],
) -> None:
    dispatch = EvaluatorDispatchService().prepare_dispatch(
        DispatchEvaluatorsCommand(
            run_id=run_id,
            task_id=task_id,
            execution_id=execution_id,
            experiment_id=experiment_id,
        )
    )

    for evaluator_id in dispatch.invalid_evaluator_ids:
        queries.task_evaluators.mark_failed(evaluator_id)

    for evaluator in dispatch.valid_evaluators:
        queries.task_evaluators.mark_running(evaluator.evaluator_id)
        evaluation_service = RubricEvaluationService(
            criterion_executor=SequentialCriterionExecutor(
                run_id=run_id,
                task_id=task_id,
                sandbox_manager=sandbox_manager,
                judge_responses=judge_responses,
            )
        )
        task_context = TaskEvaluationContext(
            run_id=run_id,
            task_input=evaluator.task_input,
            agent_reasoning=evaluator.agent_reasoning,
            agent_outputs=evaluator.agent_outputs,
        )
        result = await evaluation_service.evaluate(task_context, evaluator.rubric)
        result.run_id = run_id

        for criterion_dict in result.criterion_results:
            criterion_dict["run_id"] = run_id
            queries.criterion_results.create(CriterionResult.model_validate(criterion_dict))
        serialized_result = TaskEvaluationResult.model_validate(result.model_dump(mode="json"))
        queries.task_evaluation_results.create(serialized_result)
        queries.task_evaluators.mark_completed(evaluator.evaluator_id, result.normalized_score)

        execution = queries.task_executions.get(execution_id)
        if execution is None:
            raise ValueError(f"Task execution {execution_id} not found")
        queries.task_executions.update(
            execution.model_copy(
                update={
                    "score": result.normalized_score,
                    "evaluation_details": result.model_dump(mode="json"),
                }
            )
        )


async def _execute_deterministic_case(case: DeterministicCase) -> DeterministicRunResult:
    """Execute one deterministic benchmark case inside an existing runtime session."""
    worker = ScriptedWorker(case)
    task = Task(
        name=case.task_name,
        description=case.task_description,
        assigned_to=worker,
        resources=case.resources,
        evaluator=case.evaluator,
    )

    benchmark_name = BenchmarkName(case.benchmark_name)
    validate_task_dag(task)
    store_workers_from_task(task)

    try:
        agent_registry = AgentRegistry()
        agent_registry.register_from_task(task)
        experiment, run, _resource_mapping = persist_workflow(
            task=task,
            worker_model=worker.model,
            max_questions=10,
            benchmark_name=benchmark_name.value,
        )
        agent_registry.persist(run.id)
        persist_agent_mapping(run.id, agent_registry)

        output_dir = settings.runs_dir / str(run.id) / "tasks" / str(task.id)
        output_dir.mkdir(parents=True, exist_ok=True)

        with capture_trace_sink() as sink:
            workflow_trace_context = workflow_start_context(
                run.id,
                attributes={"experiment_id": experiment.id},
            )
            initialized = WorkflowInitializationService(
                trace_sink=sink,
                trace_context=workflow_trace_context,
            ).initialize(
                InitializeWorkflowCommand(
                    run_id=run.id,
                    experiment_id=experiment.id,
                )
            )

            if len(initialized.initial_ready_tasks) != 1:
                raise ValueError(
                    f"Deterministic harness expects exactly one ready task, got {len(initialized.initial_ready_tasks)}"
                )

            prepared = TaskExecutionService(
                trace_sink=sink,
                trace_context=task_execute_context(
                    run.id,
                    task.id,
                    attributes={"experiment_id": experiment.id},
                ),
            ).prepare(
                PrepareTaskExecutionCommand(
                    run_id=run.id,
                    experiment_id=experiment.id,
                    task_id=task.id,
                )
            )
            if prepared.execution_id is None:
                raise ValueError(f"Task {task.id} missing execution_id")

            base_sandbox_manager = get_sandbox_manager(benchmark_name)
            sandbox_manager = SandboxManagerProxy(
                delegate=base_sandbox_manager,
                scripted_skill_responses=case.scripted_skill_responses,
            )
            input_resources = [
                queries.resources.get(resource_id)
                for resource_id in prepared.input_resource_ids
            ]
            typed_input_resources = [resource for resource in input_resources if resource is not None]
            sandbox_result = await _create_sandbox(
                run_id=run.id,
                task_id=task.id,
                sandbox_manager=sandbox_manager,
                skills_dir=get_skills_dir(benchmark_name),
                output_dir=output_dir,
                input_resources=typed_input_resources,
                envs=None,
            )

            stakeholder = ScriptedStakeholder(case.stakeholder_answers, case.name)
            toolkit = _build_toolkit(
                case,
                task_id=task.id,
                run_id=run.id,
                experiment_id=experiment.id,
                stakeholder=stakeholder,
                sandbox_manager=sandbox_manager,
            )

            agent_config = await _get_or_create_worker_config(run.id, worker)
            await _link_execution_to_agent(prepared.execution_id, agent_config.id)
            await _get_or_create_stakeholder_config(run.id, benchmark_name, stakeholder)

            worker_result = await _execute_worker(
                run_id=run.id,
                task_id=task.id,
                execution_id=prepared.execution_id,
                experiment=experiment,
                task_description=prepared.task_description,
                agent_config=agent_config,
                worker=worker,
                toolkit=toolkit,
                sandbox_manager=sandbox_manager,
                input_resources=typed_input_resources,
            )
            if not worker_result.success:
                TaskExecutionService().finalize_failure(
                    FailTaskExecutionCommand(
                        execution_id=prepared.execution_id,
                        run_id=run.id,
                        task_id=task.id,
                        error_message=worker_result.error or "Scripted worker failed",
                    )
                )
                raise RuntimeError(worker_result.error or "Scripted worker failed")

            output_resource_ids = await _persist_outputs(
                run_id=run.id,
                task_id=task.id,
                execution_id=prepared.execution_id,
                output_dir=Path(sandbox_result.output_dir),
                sandbox_manager=sandbox_manager,
                input_resource_ids=prepared.input_resource_ids,
            )

            TaskExecutionService().finalize_success(
                FinalizeTaskExecutionCommand(
                    execution_id=prepared.execution_id,
                    output_text=worker_result.output_text,
                    output_resource_ids=output_resource_ids,
                )
            )

            current_run = queries.runs.get(run.id)
            if current_run is None:
                raise ValueError(f"Run {run.id} not found")
            queries.runs.update(
                current_run.model_copy(
                    update={
                        "questions_asked": worker_result.questions_asked,
                        "output_resource_ids": [str(resource_id) for resource_id in output_resource_ids],
                    }
                )
            )

            TaskPropagationService(
                trace_sink=sink,
                trace_context=task_execute_context(
                    run.id,
                    task.id,
                    execution_id=prepared.execution_id,
                    attributes={"experiment_id": experiment.id},
                ),
            ).propagate(
                PropagateTaskCompletionCommand(
                    run_id=run.id,
                    experiment_id=experiment.id,
                    task_id=task.id,
                    execution_id=prepared.execution_id,
                )
            )

            await _run_evaluators(
                run_id=run.id,
                task_id=task.id,
                execution_id=prepared.execution_id,
                experiment_id=experiment.id,
                sandbox_manager=sandbox_manager,
                judge_responses=deque(case.scripted_judge_responses),
            )

            WorkflowFinalizationService().finalize(
                FinalizeWorkflowCommand(
                    run_id=run.id,
                )
            )

            run_after_finalize = queries.runs.get(run.id)
            if run_after_finalize and run_after_finalize.e2b_sandbox_id:
                await sandbox_manager.terminate(task.id, reason="completed")
                refreshed_run = queries.runs.get(run.id)
                if refreshed_run is not None:
                    queries.runs.update(
                        refreshed_run.model_copy(update={"e2b_sandbox_id": None})
                    )

            transcript = sink.to_transcript()

        return DeterministicRunResult(
            case=case,
            run_id=run.id,
            experiment_id=experiment.id,
            task_id=task.id,
            execution_id=prepared.execution_id,
            transcript=transcript,
        )
    finally:
        clear_workers_from_task(task)


async def run_deterministic_case(case: DeterministicCase) -> DeterministicRunResult:
    """Execute one deterministic benchmark case in-process."""
    async with deterministic_runtime_session():
        return await _execute_deterministic_case(case)


async def run_deterministic_cases_concurrently(
    cases: list[DeterministicCase],
) -> list[DeterministicRunResult]:
    """Execute multiple deterministic benchmark cases concurrently on one loop."""
    async with deterministic_runtime_session():
        return list(await gather(*(_execute_deterministic_case(case) for case in cases)))
