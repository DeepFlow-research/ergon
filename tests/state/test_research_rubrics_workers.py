"""Unit tests for ResearchRubrics worker subclasses.

Verifies that each worker instantiates cleanly and produces the expected
tool set after execute() setup.  Uses stubs to avoid real sandbox or
model calls.
"""

from collections.abc import AsyncGenerator
from typing import ClassVar
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from ergon_core.api.generation import GenerationTurn
from ergon_core.api.task_types import BenchmarkTask
from ergon_core.api.worker_context import WorkerContext

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_context(*, with_node_id: bool = True) -> WorkerContext:
    return WorkerContext(
        run_id=uuid4(),
        definition_id=uuid4(),
        task_id=uuid4(),
        execution_id=uuid4(),
        sandbox_id="fake-sandbox",
        node_id=uuid4() if with_node_id else None,
    )


def _make_task() -> BenchmarkTask:
    return BenchmarkTask(
        task_key="test-task",
        instance_key="default",
        description="Test research question",
    )


# ---------------------------------------------------------------------------
# ResearchRubricsResearcherWorker
# ---------------------------------------------------------------------------


class TestResearcherWorker:
    def test_instantiates_with_correct_slug(self):
        from ergon_builtins.workers.research_rubrics.researcher_worker import (
            ResearchRubricsResearcherWorker,
        )

        worker = ResearchRubricsResearcherWorker(name="test-researcher")
        assert worker.type_slug == "researchrubrics-researcher"
        assert worker.tools == []

    @pytest.mark.asyncio
    async def test_execute_builds_tools(self):
        from ergon_builtins.workers.research_rubrics.researcher_worker import (
            ResearchRubricsResearcherWorker,
        )

        worker = ResearchRubricsResearcherWorker(
            name="test-researcher",
            model="openai:gpt-4o",
        )
        context = _make_context()
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
        assert len(worker.tools) == 12

        # Verify tool names include expected subsets
        tool_names = {_tool_name(t) for t in worker.tools}
        assert "exa_search" in tool_names
        assert "exa_qa" in tool_names
        assert "exa_get_content" in tool_names
        assert "write_report_draft" in tool_names
        assert "edit_report_draft" in tool_names
        assert "read_report_draft" in tool_names
        # Graph tools
        assert "list_my_resources" in tool_names
        assert "list_child_resources" in tool_names


# ---------------------------------------------------------------------------
# ResearchRubricsManagerWorker
# ---------------------------------------------------------------------------


class TestManagerWorker:
    def test_instantiates_with_correct_slug(self):
        from ergon_builtins.workers.research_rubrics.manager_worker import (
            ResearchRubricsManagerWorker,
        )

        worker = ResearchRubricsManagerWorker(name="test-manager")
        assert worker.type_slug == "researchrubrics-manager"
        assert worker.tools == []

    @pytest.mark.asyncio
    async def test_requires_node_id(self):
        from ergon_builtins.workers.research_rubrics.manager_worker import (
            ResearchRubricsManagerWorker,
        )

        worker = ResearchRubricsManagerWorker(
            name="test-manager",
            model="openai:gpt-4o",
        )
        context = _make_context(with_node_id=False)
        task = _make_task()

        with pytest.raises(RuntimeError, match="requires WorkerContext.node_id"):
            async for _ in worker.execute(task, context=context):
                pass

    @pytest.mark.asyncio
    async def test_execute_builds_tools(self):
        from ergon_builtins.workers.research_rubrics.manager_worker import (
            ResearchRubricsManagerWorker,
        )

        worker = ResearchRubricsManagerWorker(
            name="test-manager",
            model="openai:gpt-4o",
        )
        context = _make_context(with_node_id=True)
        task = _make_task()

        with patch(
            "ergon_builtins.workers.baselines.react_worker.ReActWorker.execute",
            return_value=_empty_gen(),
        ):
            turns = []
            async for turn in worker.execute(task, context=context):
                turns.append(turn)

        # After execute, tools should be populated:
        # 7 subtask lifecycle tools + 6 graph tools = 13
        assert len(worker.tools) == 13

        tool_names = {_tool_name(t) for t in worker.tools}
        assert "add_subtask" in tool_names
        assert "plan_subtasks" in tool_names
        assert "cancel_task" in tool_names
        assert "refine_task" in tool_names
        assert "list_subtasks" in tool_names
        assert "get_subtask" in tool_names
        assert "bash" in tool_names
        assert "list_my_resources" in tool_names
        assert "list_child_resources" in tool_names


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _empty_gen() -> AsyncGenerator[GenerationTurn, None]:
    return
    yield  # type: ignore[misc]  # makes this a generator


def _tool_name(tool: object) -> str:
    """Extract a name from a pydantic-ai Tool or a plain callable."""
    if hasattr(tool, "name"):
        return tool.name  # type: ignore[union-attr]
    if hasattr(tool, "__name__"):
        return tool.__name__  # type: ignore[union-attr]
    return repr(tool)
