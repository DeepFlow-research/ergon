import time
from collections.abc import AsyncGenerator
from typing import ClassVar
from uuid import UUID

from ergon_core.core.generation import ContextPartChunk
from ergon_core.core.runtime.resources import RunResourceView
from ergon_core.api.task_types import BenchmarkTask
from ergon_core.api.worker_context import WorkerContext
from ergon_builtins.benchmarks.researchrubrics.sandbox_manager import (
    ResearchRubricsSandboxManager,
)

from ergon_builtins.benchmarks.researchrubrics.toolkit_types import (
    ReportReadFailure,
    ReportReadResponse,
    ReportReadSuccess,
    ReportWriteFailure,
    ReportWriteResponse,
    ReportWriteSuccess,
)
from ergon_builtins.tools.graph_toolkit import ResearchGraphToolkit
from ergon_builtins.tools.research_rubrics_toolkit import ResearchRubricsToolkit
from ergon_builtins.tools.workflow_cli_tool import make_workflow_cli_tool
from ergon_builtins.workers.baselines.react_worker import ReActWorker
from ergon_builtins.workers.baselines.tool_budget import (
    AgentToolBudgetDeps,
    AgentToolBudgetState,
)
from ergon_builtins.workers.research_rubrics._run_skill import (
    ReportEditSkillRequest,
    ReportReadSkillRequest,
    ReportWriteSkillRequest,
    SkillRequest,
    SkillResponse,
    make_run_skill,
)

_WORKFLOW_PROMPT = (
    "Role: You are a recursive ResearchRubrics research agent with workflow access.\n\n"
    "Goal: Produce `final_output/report.md` with a well-sourced answer to the task. "
    "Include a # Findings section and a ## Sources section with citations.\n\n"
    "Tools:\n"
    "- `workflow(command)`: inspect task topology/resources and create subtasks. "
    "Use it deliberately; workflow calls are limited. Useful commands include "
    "`inspect task-tree`, `inspect resource-list --scope input`, "
    "`inspect resource-list --scope visible --limit 20`, `inspect next-actions`, "
    "and `manage materialize-resource --resource-id <id> --dry-run`.\n"
    "- `exa_search`: broad web search for candidate sources.\n"
    "- `exa_qa`: focused Q&A when one specific fact or synthesis is missing.\n"
    "- `exa_get_content`: read a specific URL that looks important.\n"
    "- `write_report_draft` / `edit_report_draft` / `read_report_draft`: create, "
    "revise, and inspect markdown report files.\n"
    "- Resource discovery tools: inspect resources produced by this task, children, "
    "descendants, or the run.\n\n"
    "Task graph policy: At the start of your task, use workflow context before "
    "deep research: `inspect task-tree --format json` and "
    "`inspect next-actions --manager-capable`. Use that context to decide whether "
    "to solve directly or create subtasks. Create subtasks when the work can be "
    "parallelized into independent evidence-gathering or checking efforts, such "
    "as source scouting, rubric-cluster coverage, factual sections, or risk/negative "
    "constraint checks. Do not create subtasks just to avoid writing; if the task "
    "is already narrow, answer it directly. Good subtasks have clear deliverables "
    "and produce evidence artifacts for synthesis. Prefer a small number of useful "
    "subtasks over many tiny ones. Child subtasks should usually use worker "
    "`researchrubrics-workflow-cli-react` too, so the same decision policy applies "
    "recursively. Use `researchrubrics-researcher` only for a narrow leaf task that "
    "should not create further subtasks. First dry-run commands like "
    "`manage add-task --task-slug source-scout --worker "
    "researchrubrics-workflow-cli-react --description 'Find high-quality sources "
    "for ...' --dry-run`, then repeat without `--dry-run` once correct. If you "
    "create subtasks, wait for them to finish before final synthesis, then inspect "
    "their resources. If a subtask fails or is cancelled, inspect what is missing "
    "and decide whether to proceed with available evidence or create one replacement "
    "task with a narrower scope.\n\n"
    "Stop rules: Use the fewest useful tool loops. Search again only if a required "
    "fact/source is missing. Do not search to improve phrasing or collect "
    "nonessential detail. If current evidence can answer the core task, write the "
    "report. If any tool returns TOOL_BUDGET_EXHAUSTED, stop polling/searching and "
    "produce the best possible final output from current context/resources."
)

_TOOL_BUDGET_LIMITS = {
    "max_workflow_tool_calls": 12,
    "max_other_tool_calls": 12,
}


def _workspace_path(relative_path: str) -> str:
    cleaned = relative_path.lstrip("/")
    if not cleaned or ".." in cleaned.split("/"):
        raise ValueError(f"path escapes /workspace: {relative_path!r}")
    return f"/workspace/{cleaned}"


class ResearchRubricsWorkflowCliReActWorker(ReActWorker):
    type_slug: ClassVar[str] = "researchrubrics-workflow-cli-react"

    def __init__(
        self,
        *,
        name: str,
        model: str | None,
        task_id: UUID,
        sandbox_id: str,
    ) -> None:
        super().__init__(
            name=name,
            model=model,
            task_id=task_id,
            sandbox_id=sandbox_id,
            tools=[],
            system_prompt=_WORKFLOW_PROMPT,
            max_iterations=60,
        )
        self._agent_deps = AgentToolBudgetDeps(
            tool_budget=AgentToolBudgetState(
                max_workflow_tool_calls=_TOOL_BUDGET_LIMITS["max_workflow_tool_calls"],
                max_other_tool_calls=_TOOL_BUDGET_LIMITS["max_other_tool_calls"],
            ),
        )

    def build_agent_deps(self, context: WorkerContext) -> AgentToolBudgetDeps:
        return self._agent_deps

    async def execute(
        self,
        task: BenchmarkTask,
        *,
        context: WorkerContext,
    ) -> AsyncGenerator[ContextPartChunk, None]:
        manager = ResearchRubricsSandboxManager()
        model_run_skill = make_run_skill(model=self.model)

        async def run_skill(request: SkillRequest) -> SkillResponse:
            if isinstance(
                request,
                (ReportWriteSkillRequest, ReportEditSkillRequest, ReportReadSkillRequest),
            ):
                return await self._run_sandbox_report_skill(manager=manager, request=request)
            return await model_run_skill(request)

        async def publisher_sync() -> list[RunResourceView]:
            publisher = manager.publisher_for(
                task_id=self.task_id,
                run_id=context.run_id,
                task_execution_id=context.execution_id,
            )
            return await publisher.sync()

        rr_toolkit = ResearchRubricsToolkit(
            run_skill=run_skill,
            publisher_sync=publisher_sync,
        )
        graph_toolkit = ResearchGraphToolkit(
            run_id=context.run_id,
            task_execution_id=context.execution_id,
        )
        workflow_tool = make_workflow_cli_tool(
            worker_context=context,
            sandbox_task_key=self.task_id,
            benchmark_type="researchrubrics",
            budgeted=True,
        )
        self._agent_deps = AgentToolBudgetDeps(
            tool_budget=AgentToolBudgetState(
                max_workflow_tool_calls=_TOOL_BUDGET_LIMITS["max_workflow_tool_calls"],
                max_other_tool_calls=_TOOL_BUDGET_LIMITS["max_other_tool_calls"],
            ),
        )
        self.tools = [*rr_toolkit.build_tools(), *graph_toolkit.build_tools(), workflow_tool]

        async for chunk in super().execute(task, context=context):
            yield chunk

    async def _run_sandbox_report_skill(
        self,
        *,
        manager: ResearchRubricsSandboxManager,
        request: ReportWriteSkillRequest | ReportEditSkillRequest | ReportReadSkillRequest,
    ) -> ReportWriteResponse | ReportReadResponse:
        started = time.perf_counter()
        try:
            path = _workspace_path(request.relative_path)
        except ValueError as exc:
            latency_ms = (time.perf_counter() - started) * 1000
            if isinstance(request, ReportReadSkillRequest):
                return ReportReadFailure(
                    path=request.relative_path,
                    reason="path_disallowed",
                    detail=str(exc),
                    latency_ms=latency_ms,
                )
            return ReportWriteFailure(
                path=request.relative_path,
                reason="path_disallowed",
                detail=str(exc),
                latency_ms=latency_ms,
            )

        try:
            if isinstance(request, ReportReadSkillRequest):
                latency_ms = (time.perf_counter() - started) * 1000
                content = await manager.read_report_file(
                    task_id=self.task_id,
                    workspace_path=path,
                    duration_ms=int(latency_ms),
                )
                return ReportReadSuccess(
                    path=path,
                    content=content,
                    size_bytes=len(content.encode("utf-8")),
                    latency_ms=latency_ms,
                )

            content = (
                request.content if isinstance(request, ReportWriteSkillRequest) else request.patch
            )
            latency_ms = (time.perf_counter() - started) * 1000
            await manager.write_report_file(
                task_id=self.task_id,
                workspace_path=path,
                content=content,
                duration_ms=int(latency_ms),
            )
            return ReportWriteSuccess(
                path=path,
                bytes_written=len(content.encode("utf-8")),
                latency_ms=latency_ms,
            )
        except Exception as exc:  # slopcop: ignore[no-broad-except]
            latency_ms = (time.perf_counter() - started) * 1000
            if isinstance(request, ReportReadSkillRequest):
                return ReportReadFailure(
                    path=path,
                    reason="unknown",
                    detail=f"{type(exc).__name__}: {exc}",
                    latency_ms=latency_ms,
                )
            return ReportWriteFailure(
                path=path,
                reason="unknown",
                detail=f"{type(exc).__name__}: {exc}",
                latency_ms=latency_ms,
            )
