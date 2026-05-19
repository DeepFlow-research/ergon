"""Serializable ResearchRubrics toolkit config (v2 authoring shape).

Carries only config (judge model selection, search-call budget, network
toggle).  Runtime tool handles are built lazily via ``tools(sandbox, task)``;
they are not serializable and never round-trip through JSON.
"""

from typing import Any

from ergon_core.api import Task
from ergon_core.api.sandbox import Sandbox
from pydantic_ai.tools import Tool

from ergon_builtins.toolkits.common.base import Toolkit


# ---------------------------------------------------------------------------
# ResearchRubricsToolkit — v2 authoring config
# ---------------------------------------------------------------------------


class ResearchRubricsToolkit(Toolkit):
    """Serializable ResearchRubrics toolkit config.

    The ``_type`` discriminator serializer is inherited from ``Toolkit``,
    so the toolkit round-trips through ``task_json`` snapshots alongside
    the worker without any extra boilerplate here.
    """

    judge_model: str = "openai:gpt-4o"
    max_search_calls: int = 12
    enable_web_browse: bool = True
    workspace_root: str = "/workspace"

    def tools(self, sandbox: Sandbox, task: Task[Any]) -> list[Tool]:
        """Build live pydantic_ai Tool instances bound to the v2 sandbox."""
        # reason: circular import — benchmarks/researchrubrics/toolkit.py →
        # benchmarks/researchrubrics/tools/tool_builder.py → benchmarks/researchrubrics/toolkit.py
        from ergon_builtins.benchmarks.researchrubrics.tools.tool_builder import build_tools

        return build_tools(self, sandbox=sandbox, task=task)
