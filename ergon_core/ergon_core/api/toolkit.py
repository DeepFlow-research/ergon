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

from pydantic import BaseModel, ConfigDict, model_serializer, model_validator

from ergon_core.api._serialization import import_component


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

    @model_validator(mode="wrap")
    @classmethod
    def _dispatch_subclass(
        cls,
        data: Any,  # slopcop: ignore[no-typing-any]
        handler: Callable[[Any], "Toolkit"],  # slopcop: ignore[no-typing-any]
    ) -> "Toolkit":
        # When a nested ``Toolkit | None`` field deserializes from JSON,
        # Pydantic invokes validation on the *declared* base class. Without
        # this hook, ``ReActWorker.model_validate({..., "toolkit": {...}})``
        # would try to instantiate the abstract ``Toolkit`` directly and
        # raise ``TypeError``. We instead resolve the concrete subclass
        # from ``_type`` and delegate to its own ``model_validate``.
        if isinstance(data, dict) and cls is Toolkit:
            type_path = data.get("_type")
            if isinstance(type_path, str):
                ConcreteCls = import_component(type_path)
                return ConcreteCls.model_validate(  # ty: ignore[invalid-return-type]
                    {k: v for k, v in data.items() if k != "_type"}
                )
        return handler(data)

    @abstractmethod
    def tools(self, sandbox: Any, task: Any) -> list:  # slopcop: ignore[no-typing-any]
        """Build live pydantic_ai Tool instances bound to a sandbox + task."""
