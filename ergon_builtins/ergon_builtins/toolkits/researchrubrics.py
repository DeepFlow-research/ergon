"""ResearchRubrics ReAct toolkit spec."""

import time
from typing import Any
from uuid import UUID

from ergon_core.api import Sandbox, Task, WorkerContext
from ergon_core.core.application.resources import RunResourceView
from ergon_builtins.benchmarks.researchrubrics.sandbox_manager import ResearchRubricsSandbox
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
from ergon_builtins.toolkits.react import ReActToolkit
from ergon_builtins.workers.research_rubrics._run_skill import (
    ReportEditSkillRequest,
    ReportReadSkillRequest,
    ReportWriteSkillRequest,
    SkillRequest,
    SkillResponse,
    make_run_skill,
)
from ergon_builtins.workers.baselines.tool_budget import (
    AgentToolBudgetDeps,
    AgentToolBudgetState,
)

TOOL_BUDGET_LIMITS = {
    "max_workflow_tool_calls": 12,
    "max_other_tool_calls": 12,
}


def _workspace_path(relative_path: str) -> str:
    cleaned = relative_path.lstrip("/")
    if not cleaned or ".." in cleaned.split("/"):
        raise ValueError(f"path escapes /workspace: {relative_path!r}")
    return f"/workspace/{cleaned}"


class ResearchRubricsWorkflowToolkit(ReActToolkit):
    """Materialize ResearchRubrics graph, workflow, and report tools."""

    model: str | None = None

    def build_agent_deps(
        self,
        *,
        context: WorkerContext,
    ) -> AgentToolBudgetDeps:
        del context
        return AgentToolBudgetDeps(
            tool_budget=AgentToolBudgetState(
                max_workflow_tool_calls=TOOL_BUDGET_LIMITS["max_workflow_tool_calls"],
                max_other_tool_calls=TOOL_BUDGET_LIMITS["max_other_tool_calls"],
            ),
        )

    def build_tools(
        self,
        *,
        task: Task,
        context: WorkerContext,
        sandbox: Sandbox,
    ) -> list[Any]:  # slopcop: ignore[no-typing-any]
        if not isinstance(sandbox, ResearchRubricsSandbox):
            raise TypeError(
                f"ResearchRubricsWorkflowToolkit requires ResearchRubricsSandbox, "
                f"got {type(sandbox).__name__}"
            )
        model_run_skill = make_run_skill(model=self.model)

        async def run_skill(request: SkillRequest) -> SkillResponse:
            if isinstance(
                request,
                (ReportWriteSkillRequest, ReportEditSkillRequest, ReportReadSkillRequest),
            ):
                return await _run_sandbox_report_skill(sandbox=sandbox, request=request)
            return await model_run_skill(request)

        async def publisher_sync() -> list[RunResourceView]:
            return []

        rr_toolkit = ResearchRubricsToolkit(run_skill=run_skill, publisher_sync=publisher_sync)
        graph_toolkit = ResearchGraphToolkit(
            run_id=context.run_id,
            task_execution_id=context.execution_id,
        )
        workflow_tool = make_workflow_cli_tool(
            worker_context=context,
            sandbox_task_key=task.task_id,
            benchmark_type="researchrubrics",
            budgeted=True,
        )
        return [*rr_toolkit.build_tools(), *graph_toolkit.build_tools(), workflow_tool]


async def _run_sandbox_report_skill(
    *,
    sandbox: ResearchRubricsSandbox,
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
            content = await sandbox.read_report_file(
                task_id=UUID(int=0),
                workspace_path=path,
                duration_ms=int(latency_ms),
            )
            return ReportReadSuccess(
                path=path,
                content=content,
                size_bytes=len(content.encode("utf-8")),
                latency_ms=latency_ms,
            )

        content = request.content if isinstance(request, ReportWriteSkillRequest) else request.patch
        latency_ms = (time.perf_counter() - started) * 1000
        await sandbox.write_report_file(
            task_id=UUID(int=0),
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
