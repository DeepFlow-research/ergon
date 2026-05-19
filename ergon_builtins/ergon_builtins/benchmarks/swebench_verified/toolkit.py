"""Serializable SWE-Bench toolkit config (v2 authoring shape).

Carries only config (file paths, limits, flags).  Runtime tool handles are
built lazily via ``tools(sandbox, task)``; they are not serializable and
never round-trip through JSON.
"""

from typing import Any

from ergon_builtins.workers.toolkit import Toolkit


class SWEBenchToolkit(Toolkit):
    """Serializable SWE-Bench toolkit config.

    The ``_type`` discriminator serializer is inherited from ``Toolkit``,
    so the toolkit round-trips through ``task_json`` snapshots alongside
    the worker without any extra boilerplate here.
    """

    repo_root: str = "/workspace/repo"
    patch_output_path: str = "/workspace/final_output/patch.diff"
    max_tool_calls: int = 32

    def tools(self, sandbox: Any, task: Any) -> list:  # slopcop: ignore[no-typing-any]
        """Build live pydantic_ai Tool instances bound to the v2 sandbox."""
        # reason: circular import — benchmarks/swebench_verified/toolkit.py →
        # benchmarks/swebench_verified/tools/tool_builder.py → benchmarks/swebench_verified/toolkit.py
        from ergon_builtins.benchmarks.swebench_verified.tools.tool_builder import build_tools

        return build_tools(self, sandbox=sandbox, task=task)
