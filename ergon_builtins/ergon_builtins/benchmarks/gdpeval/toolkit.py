"""Serializable GDPEval toolkit config (v2 authoring shape).

Carries only config (file paths, limits, flags).  Runtime tool handles
are built lazily via ``tools(sandbox, task)``; they are not serializable
and never round-trip through JSON.
"""

from typing import Any

from ergon_builtins.workers.toolkit import Toolkit


class GDPEvalToolkit(Toolkit):
    """Serializable GDPEval toolkit config.

    The ``_type`` discriminator serializer is inherited from ``Toolkit``,
    so the toolkit round-trips through ``task_json`` snapshots alongside
    the worker without any extra boilerplate here.
    """

    final_output_dir: str = "/workspace/final_output"
    inputs_dir: str = "/inputs"
    scratchpad_dir: str = "/workspace/scratchpad"
    max_tool_calls: int = 64
    allow_stakeholder_questions: bool = False

    def tools(self, sandbox: Any, task: Any) -> list:  # slopcop: ignore[no-typing-any]
        """Build live pydantic_ai Tool instances bound to the v2 sandbox."""
        # reason: circular import — benchmarks/gdpeval/toolkit.py →
        # benchmarks/gdpeval/_tools.py → benchmarks/gdpeval/toolkit.py
        from ergon_builtins.benchmarks.gdpeval._tools import build_tools

        return build_tools(self, sandbox=sandbox, task=task)
