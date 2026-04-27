from collections.abc import AsyncGenerator
import time
from typing import ClassVar
from uuid import UUID

from ergon_core.api import RunResourceView
from ergon_core.api.generation import GenerationTurn
from ergon_core.api.task_types import BenchmarkTask
from ergon_core.api.worker_context import WorkerContext
from ergon_core.core.providers.sandbox.research_rubrics_manager import (
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
from ergon_builtins.workers.research_rubrics._run_skill import (
    ReportEditSkillRequest,
    ReportReadSkillRequest,
    ReportWriteSkillRequest,
    SkillRequest,
    SkillResponse,
    make_run_skill,
)

_WORKFLOW_PROMPT = (
    "You are a research agent. Your job is to investigate a research question "
    "using web search and produce a well-sourced report.\n\n"
    "You have access to:\n"
    "- exa_search: Search the web for relevant sources\n"
    "- exa_qa: Ask Exa a direct question\n"
    "- exa_get_content: Extract full text from a URL\n"
    "- write_report_draft: Write a markdown report draft\n"
    "- edit_report_draft: Edit an existing draft\n"
    "- read_report_draft: Read a draft file\n"
    "- workflow: Inspect current-run task topology and resources\n\n"
    "Write your final report to 'final_output/report.md' using write_report_draft. "
    "Include a # Findings section and a ## Sources section with citations.\n\n"
    "Hard operating budget: use at most 6 exa_search calls for your own work. "
    "After that, write the report from the evidence you have. Prefer targeted "
    "queries over broad exploration.\n\n"
    "Use workflow(command) to inspect this run before "
    "deciding what context is missing. Useful commands include: "
    "`inspect task-workspace --format json`, `inspect task-tree`, "
    "`inspect resource-list --scope input`, "
    "`inspect resource-list --scope visible --limit 20`, "
    "`inspect resource-location --resource-id <id>`, "
    "`inspect next-actions`, and "
    "`manage materialize-resource --resource-id <id> --dry-run`. "
    "Use `--format json` when you need stable IDs. Resource copies are snapshots: "
    "materialized files become resources owned by this task, not edits to the source.\n\n"
    'First call `workflow("inspect task-workspace --format json")`. Use only '
    "`task_workspace.task.level` from that response to decide whether this current "
    "task may delegate. Ignore level-0 tasks shown elsewhere in task-tree. If "
    "`task_workspace.task.level is exactly 0`, create exactly three specialist "
    "child tasks before researching: "
    "(1) a source scout for finding citations, "
    "(2) a rubric compliance checker for mapping requirements to an outline, and "
    "(3) a synthesis reviewer for risks, gaps, and counterclaims. "
    'Use `workflow("manage add-task --task-slug <short_unique_slug> --worker worker '
    "--description '<specialist task description>'\")` for each child. "
    "Give each child a role-specific description that includes the original task "
    "goal and asks for a concise markdown report in `final_output/report.md`. "
    "Then continue your own report; do not wait for child results unless visible "
    "resources are already available.\n\n"
    "If your current `task_workspace.task.level` is not 0, you are already a "
    "specialist child. You must do only your assigned specialist work; do not call "
    '`workflow("manage add-task` under any '
    "circumstances. Do not inspect the workflow repeatedly. Use at most 2 "
    "workflow inspections and at most 3 exa_search calls, then write your "
    "specialist markdown report to `final_output/report.md`."
)


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
            max_iterations=25,
        )

    async def execute(
        self,
        task: BenchmarkTask,
        *,
        context: WorkerContext,
    ) -> AsyncGenerator[GenerationTurn, None]:
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
            manager_capable=True,
        )
        self.tools = [*rr_toolkit.build_tools(), *graph_toolkit.build_tools(), workflow_tool]

        async for turn in super().execute(task, context=context):
            yield turn

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
