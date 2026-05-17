"""Public Toolkit base — pydantic-serializable bundle of authoring config that
lazily constructs runtime tools.

Benchmarks subclass `Toolkit` to declare config fields (file paths,
limits, etc.) and implement `tools(sandbox, task)` which builds the
live `pydantic_ai` tool callables at worker-execute time. The
config-side round-trips through `task_json`; runtime tools never do.
"""

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ConfigDict, model_serializer


class Toolkit(BaseModel, ABC):
    """Authoring-time toolkit config; subclasses build live tools lazily."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @model_serializer(mode="wrap")
    def _serialize_with_type_discriminator(
        self,
        handler: Callable[["Toolkit"], dict[str, Any]],  # slopcop: ignore[no-typing-any]
    ) -> dict[str, Any]:  # slopcop: ignore[no-typing-any]
        """Inject ``_type`` so the toolkit snapshot round-trips in task JSON."""
        payload = handler(self)
        payload["_type"] = f"{type(self).__module__}:{type(self).__qualname__}"
        return payload

    @abstractmethod
    def tools(self, sandbox: Any, task: Any) -> list:  # slopcop: ignore[no-typing-any]
        """Build live pydantic_ai Tool instances bound to a sandbox + task."""
