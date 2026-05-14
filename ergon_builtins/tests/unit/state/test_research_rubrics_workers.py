"""Unit tests for ResearchRubrics worker subclasses.

Verifies that each worker instantiates cleanly and produces the expected
tool set after execute() setup.  Uses stubs to avoid real sandbox or
model calls.
"""

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from ergon_builtins.benchmarks.researchrubrics.toolkit_types import (
    ReportReadSuccess,
    ReportWriteSuccess,
)
from ergon_builtins.workers.research_rubrics._run_skill import (
    ReportReadSkillRequest,
    ReportWriteSkillRequest,
)
from ergon_builtins.workers.research_rubrics.researcher_worker import (
    ResearchRubricsResearcherWorker,
)
from ergon_builtins.workers.research_rubrics.workflow_cli_react_worker import (
    _WORKFLOW_PROMPT,
    ResearchRubricsWorkflowCliReActWorker,
)
from ergon_core.api.benchmark import Task
from ergon_core.api.worker import WorkerContext, WorkerStreamItem
from ergon_core.test_support.task_factory import task_with_id

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_context(*, with_node_id: bool = True) -> WorkerContext:
    return WorkerContext(
        run_id=uuid4(),
        definition_id=uuid4(),
        execution_id=uuid4(),
        sandbox_id="fake-sandbox",
        node_id=uuid4() if with_node_id else None,
    )


def _make_task() -> Task:
    return task_with_id(
        uuid4(),
        task_slug="test-task",
        instance_key="default",
        description="Test research question",
    )


# ---------------------------------------------------------------------------
# ResearchRubricsResearcherWorker
# ---------------------------------------------------------------------------


class TestResearcherWorker:
    def test_instantiates_with_correct_slug(self):
        # RFC 2026-04-22 §1 — Worker base requires task_id /
        # sandbox_id; execute() isn't called here so placeholders suffice.
        worker = ResearchRubricsResearcherWorker(
            name="test-researcher",
            model=None,
        )
        assert worker.type_slug == "researchrubrics-researcher"
        assert worker._tools == []

    @pytest.mark.asyncio
    async def test_execute_builds_tools(self):
        context = _make_context()
        worker = ResearchRubricsResearcherWorker(
            name="test-researcher",
            model="openai:gpt-4o",
        )
        task = _make_task()

        # Mock the sandbox manager and super().execute()
        fake_sandbox = MagicMock()
        fake_sandbox.files = MagicMock()
        fake_sandbox.commands = MagicMock()

        fake_manager = MagicMock()
        fake_manager.publisher_for.return_value = MagicMock()
        fake_manager.publisher_for.return_value.sync = AsyncMock(
            return_value=[],
        )

        with (
            patch(
                "ergon_builtins.workers.research_rubrics.researcher_worker"
                ".ResearchRubricsSandboxManager",
                return_value=fake_manager,
            ),
            patch(
                "ergon_builtins.workers.baselines.react_worker.ReActWorker.execute",
                return_value=_empty_gen(),
            ),
        ):
            turns = []
            async for turn in worker.execute(task, context=context):
                turns.append(turn)

        # After execute, tools should be populated:
        # 6 research-rubrics tools + 6 graph tools = 12
        assert len(worker._tools) == 12

        # Verify tool names include expected subsets
        tool_names = {_tool_name(t) for t in worker._tools}
        assert "exa_search" in tool_names
        assert "exa_qa" in tool_names
        assert "exa_get_content" in tool_names
        assert "write_report_draft" in tool_names
        assert "edit_report_draft" in tool_names
        assert "read_report_draft" in tool_names
        # Graph tools
        assert "list_my_resources" in tool_names
        assert "list_child_resources" in tool_names

    @pytest.mark.asyncio
    async def test_workflow_cli_worker_adds_workflow_tool(self):
        context = _make_context()
        worker = ResearchRubricsWorkflowCliReActWorker(
            name="test-researcher",
            model="openai:gpt-4o",
        )
        task = _make_task()

        fake_manager = MagicMock()
        fake_manager.publisher_for.return_value = MagicMock()
        fake_manager.publisher_for.return_value.sync = AsyncMock(return_value=[])

        with (
            patch(
                "ergon_builtins.workers.research_rubrics.workflow_cli_react_worker"
                ".ResearchRubricsSandboxManager",
                return_value=fake_manager,
            ),
            patch(
                "ergon_builtins.workers.baselines.react_worker.ReActWorker.execute",
                return_value=_empty_gen(),
            ),
        ):
            turns = []
            async for turn in worker.execute(task, context=context):
                turns.append(turn)

        tool_names = {_tool_name(t) for t in worker._tools}
        assert worker.type_slug == "researchrubrics-workflow-cli-react"
        assert "workflow" in tool_names

    def test_workflow_cli_prompt_exposes_real_subtask_creation(self):
        assert "manage add-task" in _WORKFLOW_PROMPT
        assert "--worker researchrubrics-workflow-cli-react" in _WORKFLOW_PROMPT
        assert "same decision policy applies recursively" in _WORKFLOW_PROMPT
        assert "--dry-run" in _WORKFLOW_PROMPT

    def test_workflow_cli_prompt_guides_recursive_task_graph_decision(self):
        assert "At the start of your task" in _WORKFLOW_PROMPT
        assert "inspect task-tree --format json" in _WORKFLOW_PROMPT
        assert "inspect next-actions --manager-capable" in _WORKFLOW_PROMPT
        assert "decide whether to solve directly or create subtasks" in _WORKFLOW_PROMPT
        assert "independent evidence-gathering or checking efforts" in _WORKFLOW_PROMPT
        assert "wait for them to finish before final synthesis" in _WORKFLOW_PROMPT
        assert "replacement task with a narrower scope" in _WORKFLOW_PROMPT

    @pytest.mark.asyncio
    async def test_report_write_uses_manager_public_file_api(self):
        task_id = uuid4()
        worker = ResearchRubricsResearcherWorker(
            name="test-researcher",
            model=None,
        )
        manager = MagicMock()
        manager.write_report_file = AsyncMock()

        result = await worker._run_sandbox_report_skill(
            manager=manager,
            task_id=task_id,
            request=ReportWriteSkillRequest(
                relative_path="final_output/report.md",
                content="# Report",
            ),
        )

        manager.write_report_file.assert_awaited_once()
        _, kwargs = manager.write_report_file.await_args
        assert kwargs["task_id"] == task_id
        assert kwargs["workspace_path"] == "/workspace/final_output/report.md"
        assert kwargs["content"] == "# Report"
        assert isinstance(result, ReportWriteSuccess)

    @pytest.mark.asyncio
    async def test_report_read_uses_manager_public_file_api(self):
        task_id = uuid4()
        worker = ResearchRubricsResearcherWorker(
            name="test-researcher",
            model=None,
        )
        manager = MagicMock()
        manager.read_report_file = AsyncMock(return_value="# Existing")

        result = await worker._run_sandbox_report_skill(
            manager=manager,
            task_id=task_id,
            request=ReportReadSkillRequest(relative_path="final_output/report.md"),
        )

        manager.read_report_file.assert_awaited_once()
        _, kwargs = manager.read_report_file.await_args
        assert kwargs["task_id"] == task_id
        assert kwargs["workspace_path"] == "/workspace/final_output/report.md"
        assert isinstance(result, ReportReadSuccess)
        assert result.content == "# Existing"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _empty_gen() -> AsyncGenerator[WorkerStreamItem, None]:
    return
    yield  # type: ignore[misc]  # makes this a generator


def _tool_name(tool: object) -> str:
    """Extract a name from a pydantic-ai Tool or a plain callable."""
    if hasattr(tool, "name"):
        return tool.name  # type: ignore[union-attr]
    if hasattr(tool, "__name__"):
        return tool.__name__  # type: ignore[union-attr]
    return repr(tool)
