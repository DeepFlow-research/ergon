"""TEST FIXTURE ONLY. Deterministic researcher stub for dashboard visibility.

Unlike ``StubWorker`` (which emits nothing beyond a single plain-text turn),
this worker is intended for ``--worker manager-researcher`` delegation-smoke
runs where the researcher sub-agent should produce enough observable activity
to populate every workspace panel on the dashboard without requiring an LLM
or an E2B sandbox:

- GENERATIONS: yields 3 ``GenerationTurn`` objects with text + tool calls +
  tool returns, so the per-turn timeline shows ``mock_web_search`` and
  ``bash`` calls.
- OUTPUTS: writes two ``RunResource`` rows (``search_result_1.md``,
  ``search_result_2.md``) pointing at content-addressed blobs on disk.
- SANDBOX: emits ``sandbox_created`` + ``sandbox_command`` dashboard events
  with deterministic commands / stdout / exit codes.
- EVALUATION: the paired ``StubCriterion`` reads its output to fill in a
  richer ``CriterionResult``.

The output is fully deterministic given a task description -- no LLM calls,
no randomness, and no real filesystem side effects outside the blob store.
"""

import hashlib
import logging
import os
from collections.abc import Awaitable
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar, cast
from uuid import UUID

from ergon_core.api import BenchmarkTask, Worker, WorkerContext, WorkerOutput
from ergon_core.api.generation import (
    GenerationTurn,
    ModelRequestPart,
    ModelResponsePart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from ergon_core.api.run_resource import RunResourceView
from ergon_core.core.dashboard.emitter import dashboard_emitter
from ergon_core.core.persistence.queries import queries
from ergon_core.core.persistence.telemetry.models import RunResourceKind
from pydantic import BaseModel

logger = logging.getLogger(__name__)

_DEFAULT_BLOB_ROOT = Path(os.environ.get("ERGON_BLOB_ROOT", "/var/ergon/blob"))
_STUB_SANDBOX_PREFIX = "stub-sandbox-"


class _MockFile(BaseModel):
    """Metadata for one deterministic mock search result file."""

    model_config = {"frozen": True}

    name: str
    size_bytes: int
    content: str


def _mock_search_content(query: str, idx: int) -> str:
    """Deterministic mock web search content for one result."""
    return (
        f"# Mock search result {idx} for: {query}\n"
        f"\n"
        f"- Finding {idx}.1: {query} has well-documented foundations in the literature.\n"
        f"- Finding {idx}.2: Recent work ({2024 - idx}) extends the core ideas.\n"
        f"- Finding {idx}.3: Open problems remain around scalability and evaluation.\n"
        f"- Source: https://example.test/refs/{idx}\n"
    )


class ResearcherStubWorker(Worker):
    """Deterministic researcher stub for delegation-smoke dashboard visibility.

    Used exclusively by the ``researcher`` binding in ``delegation-smoke``.
    Does not call any model. Does not require an E2B sandbox. Produces the
    same generations, sandbox events, outputs, and evaluation inputs every
    run for a given task description.
    """

    type_slug: ClassVar[str] = "researcher-stub"

    def __init__(self, *, name: str = "researcher-stub", model: str | None = None) -> None:
        super().__init__(name=name, model=model)

    async def execute(
        self,
        task: BenchmarkTask,
        *,
        context: WorkerContext,
    ):  # async generator of GenerationTurn
        description = task.description or task.task_key
        stub_sandbox_id = f"{_STUB_SANDBOX_PREFIX}{context.execution_id}"

        await _safe_emit(
            dashboard_emitter.sandbox_created(
                run_id=context.run_id,
                task_id=context.task_id,
                sandbox_id=stub_sandbox_id,
                timeout_minutes=5,
                template="stub",
            )
        )

        search_query = description
        search_call_id = f"call-search-{context.execution_id}"
        search_call = ToolCallPart(
            tool_name="mock_web_search",
            tool_call_id=search_call_id,
            args={"query": search_query},
        )
        turn1_user = UserPromptPart(content=f"Task: {description}")
        turn1_text = TextPart(content=f"I'll search for information about: {search_query}")

        yield GenerationTurn(
            messages_in=cast(list[ModelRequestPart], [turn1_user]),
            response_parts=cast(list[ModelResponsePart], [turn1_text, search_call]),
            tool_results=[],
            policy_version="stub-researcher-v1",
        )

        files = await _run_mock_web_search(
            run_id=context.run_id,
            task_id=context.task_id,
            task_execution_id=context.execution_id,
            sandbox_id=stub_sandbox_id,
            query=search_query,
        )

        search_tool_return = ToolReturnPart(
            tool_call_id=search_call_id,
            tool_name="mock_web_search",
            content=("Wrote 2 mock result files to sandbox: " + ", ".join(f.name for f in files)),
        )

        bash_call_id = f"call-bash-{context.execution_id}"
        bash_command = "wc -l search_result_*.md"
        bash_call = ToolCallPart(
            tool_name="bash",
            tool_call_id=bash_call_id,
            args={"command": bash_command},
        )
        synthesis = (
            f"Based on the search results: found {len(files)} mock sources covering "
            f"'{search_query}'. Key takeaways include documented foundations, recent "
            f"extensions, and remaining open problems around scalability and evaluation."
        )
        turn2_text = TextPart(content=synthesis)

        yield GenerationTurn(
            messages_in=cast(list[ModelRequestPart], [search_tool_return]),
            response_parts=cast(list[ModelResponsePart], [turn2_text, bash_call]),
            tool_results=[search_tool_return],
            policy_version="stub-researcher-v1",
        )

        bash_stdout = await _run_mock_bash(
            run_id=context.run_id,
            task_id=context.task_id,
            sandbox_id=stub_sandbox_id,
            command=bash_command,
            files=files,
        )

        bash_return = ToolReturnPart(
            tool_call_id=bash_call_id,
            tool_name="bash",
            content=bash_stdout,
        )

        final_text = TextPart(
            content=(
                f"Done. Produced {len(files)} research snippets for '{search_query}'. "
                f"bash output:\n{bash_stdout}"
            )
        )

        yield GenerationTurn(
            messages_in=cast(list[ModelRequestPart], [bash_return]),
            response_parts=cast(list[ModelResponsePart], [final_text]),
            tool_results=[bash_return],
            policy_version="stub-researcher-v1",
        )

    def get_output(self, context: WorkerContext) -> WorkerOutput:
        base = super().get_output(context)
        return WorkerOutput(
            output=base.output,
            success=True,
            metadata={"worker": "researcher-stub"},
        )


async def _run_mock_web_search(
    *,
    run_id: UUID,
    task_id: UUID,
    task_execution_id: UUID,
    sandbox_id: str,
    query: str,
) -> list[_MockFile]:
    """Write two deterministic markdown files as RunResource rows, then emit a
    sandbox_command + resource_published events so the OUTPUTS and SANDBOX
    panels populate.
    """
    started = datetime.now(UTC)

    files: list[_MockFile] = []
    for idx in (1, 2):
        name = f"search_result_{idx}.md"
        content = _mock_search_content(query, idx)
        content_bytes = content.encode("utf-8")
        content_hash = hashlib.sha256(content_bytes).hexdigest()
        blob_path = _write_blob(content_bytes, content_hash)

        prior = queries.resources.find_by_hash(
            task_execution_id=task_execution_id,
            content_hash=content_hash,
        )
        if prior is not None:
            row = prior
        else:
            row = queries.resources.append(
                run_id=run_id,
                task_execution_id=task_execution_id,
                kind=RunResourceKind.REPORT.value,
                name=name,
                mime_type="text/markdown",
                file_path=str(blob_path),
                size_bytes=len(content_bytes),
                error=None,
                content_hash=content_hash,
                metadata={"sandbox_origin": f"{sandbox_id}:/workspace/{name}"},
            )

        view = RunResourceView.from_row(row)
        files.append(_MockFile(name=name, size_bytes=len(content_bytes), content=content))

        await _safe_emit(
            dashboard_emitter.resource_published(
                run_id=run_id,
                task_id=task_id,
                task_execution_id=task_execution_id,
                resource_id=view.id,
                resource_name=name,
                mime_type="text/markdown",
                size_bytes=len(content_bytes),
                file_path=str(blob_path),
            )
        )

    ended = datetime.now(UTC)
    duration_ms = int((ended - started).total_seconds() * 1000) or 1
    await _safe_emit(
        dashboard_emitter.sandbox_command(
            run_id=run_id,
            task_id=task_id,
            sandbox_id=sandbox_id,
            command=f"mock_web_search: {query}",
            stdout="\n".join(f"wrote {f.name} ({f.size_bytes} bytes)" for f in files),
            stderr=None,
            exit_code=0,
            duration_ms=duration_ms,
        )
    )
    return files


async def _run_mock_bash(
    *,
    run_id: UUID,
    task_id: UUID,
    sandbox_id: str,
    command: str,
    files: list[_MockFile],
) -> str:
    """Produce deterministic stdout for ``wc -l search_result_*.md`` and emit
    a sandbox_command event so the SANDBOX panel shows the bash run."""
    started = datetime.now(UTC)
    lines_by_file = {f.name: f.content.count("\n") for f in files}
    total = sum(lines_by_file.values())
    stdout_lines = [f"  {count} {name}" for name, count in lines_by_file.items()]
    if len(files) > 1:
        stdout_lines.append(f"  {total} total")
    stdout = "\n".join(stdout_lines)
    ended = datetime.now(UTC)
    duration_ms = int((ended - started).total_seconds() * 1000) or 1

    await _safe_emit(
        dashboard_emitter.sandbox_command(
            run_id=run_id,
            task_id=task_id,
            sandbox_id=sandbox_id,
            command=f"bash: {command}",
            stdout=stdout,
            stderr=None,
            exit_code=0,
            duration_ms=duration_ms,
        )
    )
    return stdout


def _write_blob(content_bytes: bytes, content_hash: str) -> Path:
    path = _DEFAULT_BLOB_ROOT / content_hash[:2] / content_hash
    if path.exists():
        return path
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(content_bytes)
        tmp.rename(path)
    except OSError:
        logger.warning("researcher-stub: could not write blob at %s; skipping durable write", path)
    return path


async def _safe_emit(coro: Awaitable[None]) -> None:
    """Await ``coro``; swallow emit failures so stub execution never breaks."""
    try:
        await coro
    except Exception:  # slopcop: ignore[no-broad-except]
        logger.warning("researcher-stub: dashboard emit failed", exc_info=True)
