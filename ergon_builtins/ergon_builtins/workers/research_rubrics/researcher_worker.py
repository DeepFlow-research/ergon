"""ResearchRubrics researcher worker.

Builds the 9-tool researcher inventory (Exa + report drafting + graph
observability) at execute time from WorkerContext, then delegates to
ReActWorker.execute().
"""

from collections.abc import AsyncGenerator
import time
from typing import ClassVar
from uuid import UUID

from pydantic import BaseModel

from ergon_core.api import RunResourceView
from ergon_core.api.generation import GenerationTurn
from ergon_core.api.task_types import BenchmarkTask
from ergon_core.api.worker_context import WorkerContext
from ergon_core.core.providers.sandbox.research_rubrics_manager import (
    ResearchRubricsSandboxManager,
)

from ergon_builtins.tools.graph_toolkit import ResearchGraphToolkit
from ergon_builtins.benchmarks.researchrubrics.toolkit_types import (
    ReportReadFailure,
    ReportReadResponse,
    ReportReadSuccess,
    ReportWriteFailure,
    ReportWriteResponse,
    ReportWriteSuccess,
)
from ergon_builtins.tools.research_rubrics_toolkit import (
    ResearchRubricsToolkit,
)
from ergon_builtins.workers.baselines.react_worker import ReActWorker
from ergon_builtins.workers.research_rubrics._run_skill import (
    make_run_skill,
)

_RESEARCHER_SYSTEM_PROMPT = (
    "You are a research agent. Your job is to investigate a research question "
    "using web search and produce a well-sourced report.\n\n"
    "You have access to:\n"
    "- exa_search: Search the web for relevant sources\n"
    "- exa_qa: Ask Exa a direct question\n"
    "- exa_get_content: Extract full text from a URL\n"
    "- write_report_draft: Write a markdown report draft\n"
    "- edit_report_draft: Edit an existing draft\n"
    "- read_report_draft: Read a draft file\n"
    "- Resource discovery tools to observe peer outputs\n\n"
    "Write your final report to 'final_output/report.md' using write_report_draft. "
    "Include a # Findings section and a ## Sources section with citations."
)


def _workspace_path(relative_path: str) -> str:
    """Resolve a user path under /workspace and reject traversal."""
    cleaned = relative_path.lstrip("/")
    if not cleaned or ".." in cleaned.split("/"):
        raise ValueError(f"path escapes /workspace: {relative_path!r}")
    return f"/workspace/{cleaned}"


class ResearchRubricsResearcherWorker(ReActWorker):
    """Researcher worker for researchrubrics benchmarks.

    Builds the 9-tool researcher inventory (Exa + report drafting + graph
    observability) at execute time from WorkerContext.  The run_skill
    callable delegates to a pydantic-ai Agent for structured output.
    """

    type_slug: ClassVar[str] = "researchrubrics-researcher"

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
            system_prompt=_RESEARCHER_SYSTEM_PROMPT,
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

        async def run_skill(
            skill_name: str,
            response_model: type[BaseModel],
            **kwargs: object,
        ) -> BaseModel:
            if skill_name in {"write_report_draft", "edit_report_draft", "read_report_draft"}:
                return await self._run_sandbox_report_skill(
                    manager=manager,
                    skill_name=skill_name,
                    **kwargs,
                )
            return await model_run_skill(skill_name, response_model, **kwargs)

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
        rr_tools = rr_toolkit.build_tools()

        graph_toolkit = ResearchGraphToolkit(
            run_id=context.run_id,
            task_execution_id=context.execution_id,
        )
        graph_tools = graph_toolkit.build_tools()

        self.tools = [*rr_tools, *graph_tools]

        async for turn in super().execute(task, context=context):
            yield turn

    async def _run_sandbox_report_skill(
        self,
        *,
        manager: ResearchRubricsSandboxManager,
        skill_name: str,
        **kwargs: object,
    ) -> ReportWriteResponse | ReportReadResponse:
        started = time.perf_counter()
        try:
            relative_path = str(kwargs["relative_path"])
            path = _workspace_path(relative_path)
        except Exception as exc:
            latency_ms = (time.perf_counter() - started) * 1000
            if skill_name == "read_report_draft":
                return ReportReadFailure(
                    path=str(kwargs.get("relative_path", "")),
                    reason="path_disallowed",
                    detail=str(exc),
                    latency_ms=latency_ms,
                )
            return ReportWriteFailure(
                path=str(kwargs.get("relative_path", "")),
                reason="path_disallowed",
                detail=str(exc),
                latency_ms=latency_ms,
            )

        try:
            sandbox = manager._get_raw_sandbox(self.task_id)
            if skill_name == "read_report_draft":
                content = await sandbox.files.read(path)
                if isinstance(content, bytes):
                    content = content.decode("utf-8")
                latency_ms = (time.perf_counter() - started) * 1000
                await manager._emit_wal_entry(
                    self.task_id,
                    command=f"files.read {path}",
                    stdout=f"path={path}\nbytes={len(content.encode('utf-8'))}",
                    exit_code=0,
                    duration_ms=int(latency_ms),
                )
                return ReportReadSuccess(
                    path=path,
                    content=content,
                    size_bytes=len(content.encode("utf-8")),
                    latency_ms=latency_ms,
                )

            content = str(
                kwargs["content"] if skill_name == "write_report_draft" else kwargs["patch"],
            )
            await sandbox.files.write(path, content.encode("utf-8"))
            latency_ms = (time.perf_counter() - started) * 1000
            manager.register_created_file(self.task_id, path)
            await manager._emit_wal_entry(
                self.task_id,
                command=f"files.write {path}",
                stdout=f"path={path}\nbytes={len(content.encode('utf-8'))}",
                exit_code=0,
                duration_ms=int(latency_ms),
            )
            return ReportWriteSuccess(
                path=path,
                bytes_written=len(content.encode("utf-8")),
                latency_ms=latency_ms,
            )
        except Exception as exc:  # slopcop: ignore[no-broad-except]
            latency_ms = (time.perf_counter() - started) * 1000
            if skill_name == "read_report_draft":
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
