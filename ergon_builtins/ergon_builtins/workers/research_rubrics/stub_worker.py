"""Stub research worker for E2B smoke tests.

Writes a canned research report to /workspace/final_output/report.md in the
sandbox without calling any LLM.  After writing, triggers
``SandboxResourcePublisher.sync()`` so the report appears as a RunResource.

Used only by the ``researchrubrics-smoke`` benchmark to exercise the real-
sandbox path without paying for cloud LLM calls.
"""

from collections.abc import AsyncGenerator
from typing import ClassVar
from uuid import UUID

from e2b_code_interpreter import AsyncSandbox  # type: ignore[import-untyped]
from ergon_core.api import BenchmarkTask, Worker, WorkerContext
from ergon_core.api.generation import GenerationTurn, TextPart
from ergon_core.core.providers.sandbox.research_rubrics_manager import (
    ResearchRubricsSandboxManager,
)

REPORT_PATH = "/workspace/final_output/report.md"

STUB_REPORT_CONTENT = """\
# Stub Research Report

## Summary

This is a deterministic stub report produced by StubResearchRubricsWorker.
It exists to exercise the sandbox -> publisher -> RunResource pipeline
without requiring any LLM calls.

# Findings

1. The E2B sandbox filesystem round-trip works correctly.
2. SandboxResourcePublisher.sync() detects new files and appends rows.
3. Content-hash dedup prevents duplicate rows on repeated syncs.

## Sources

- [1] E2B Documentation, https://e2b.dev/docs
- [2] Ergon RFC C3, internal document
- [3] ResearchRubrics dataset, ScaleAI
"""


class StubResearchRubricsWorker(Worker):
    """Writes a canned research report to the sandbox.

    Used only by the E2B smoke test to exercise the real-sandbox path
    without paying for cloud LLM calls.
    """

    type_slug: ClassVar[str] = "researchrubrics-stub"

    def __init__(
        self,
        *,
        name: str = "researchrubrics-stub",
        model: str | None,
        task_id: UUID,
        sandbox_id: str,
    ) -> None:
        super().__init__(name=name, model=model, task_id=task_id, sandbox_id=sandbox_id)

    async def execute(
        self,
        task: BenchmarkTask,
        *,
        context: WorkerContext,
    ) -> AsyncGenerator[GenerationTurn, None]:
        sandbox = await AsyncSandbox.connect(sandbox_id=context.sandbox_id)

        # Ensure the output directory exists.
        await sandbox.commands.run("mkdir -p /workspace/final_output")

        # Write the deterministic report.
        await sandbox.files.write(REPORT_PATH, STUB_REPORT_CONTENT)

        # Trigger publisher sync so the report lands as a RunResource row.
        manager = ResearchRubricsSandboxManager()
        publisher = manager.publisher_for(
            task_id=context.task_id,
            run_id=context.run_id,
            task_execution_id=context.execution_id,
        )
        created = await publisher.sync()

        resource_names = [r.name for r in created]
        yield GenerationTurn(
            response_parts=[
                TextPart(
                    content=(
                        f"Wrote {REPORT_PATH} to sandbox {context.sandbox_id}. "
                        f"Published resources: {resource_names}"
                    )
                )
            ],
        )
