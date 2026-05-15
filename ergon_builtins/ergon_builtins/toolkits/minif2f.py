"""Serializable MiniF2F toolkit config (v2 authoring shape).

Carries only config (file paths, limits, flags).  Runtime tool handles are
built lazily via ``tools(sandbox, task)``; they are not serializable and
never round-trip through JSON.
"""

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ConfigDict, model_serializer


class MiniF2FToolkit(BaseModel):
    """Serializable MiniF2F toolkit config.

    The ``_type`` discriminator is injected by Pydantic's ``model_serializer``
    (inherited via the Worker → Task serialization chain) so the toolkit
    round-trips through ``task_json`` snapshots alongside the worker.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    proof_output_path: str = "/workspace/final_output/proof.lean"
    lean_workspace: str = "/workspace/lean"
    max_tool_calls: int = 32

    @model_serializer(mode="wrap")
    def _serialize_with_type_discriminator(
        self,
        handler: Callable[["MiniF2FToolkit"], dict[str, Any]],  # slopcop: ignore[no-typing-any]
    ) -> dict[str, Any]:  # slopcop: ignore[no-typing-any]
        """Inject ``_type`` so the toolkit snapshot round-trips in task JSON."""
        payload = handler(self)
        payload["_type"] = f"{type(self).__module__}:{type(self).__qualname__}"
        return payload

    def tools(self, sandbox: Any, task: Any) -> list:  # slopcop: ignore[no-typing-any]
        """Build live pydantic_ai Tool instances bound to the v2 sandbox."""
        # reason: circular import — minif2f.py → _minif2f_tools.py →
        # benchmarks.minif2f.constants (triggers benchmarks/minif2f/__init__.py) →
        # benchmark.py → worker_factory.py → minif2f.py
        from ergon_builtins.toolkits._minif2f_tools import build_tools

        return build_tools(self, sandbox=sandbox, task=task)
