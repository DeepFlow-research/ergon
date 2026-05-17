"""Serializable MiniF2F toolkit config (v2 authoring shape).

Carries only config (file paths, limits, flags).  Runtime tool handles are
built lazily via ``tools(sandbox, task)``; they are not serializable and
never round-trip through JSON.
"""

from typing import Any

from ergon_core.api.toolkit import Toolkit


class MiniF2FToolkit(Toolkit):
    """Serializable MiniF2F toolkit config.

    The ``_type`` discriminator serializer is inherited from ``Toolkit``,
    so the toolkit round-trips through ``task_json`` snapshots alongside
    the worker without any extra boilerplate here.
    """

    proof_output_path: str = "/workspace/final_output/proof.lean"
    lean_workspace: str = "/workspace/lean"
    max_tool_calls: int = 32

    def tools(self, sandbox: Any, task: Any) -> list:  # slopcop: ignore[no-typing-any]
        """Build live pydantic_ai Tool instances bound to the v2 sandbox."""
        # reason: circular import — benchmarks/minif2f/toolkit.py → benchmarks/minif2f/_tools.py →
        # benchmarks/minif2f/constants.py → benchmarks/minif2f/__init__.py →
        # benchmark.py → workers.py → benchmarks/minif2f/toolkit.py
        from ergon_builtins.benchmarks.minif2f._tools import build_tools

        return build_tools(self, sandbox=sandbox, task=task)
