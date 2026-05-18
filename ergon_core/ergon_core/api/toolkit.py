"""Public Toolkit base — pydantic-serializable bundle of authoring config that
lazily constructs runtime tools.

Benchmarks subclass `Toolkit` to declare config fields (file paths,
limits, etc.) and implement `tools(sandbox, task)` which builds the
live `pydantic_ai` tool callables at worker-execute time. The
config-side round-trips through `task_json`; runtime tools never do.
"""

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, model_serializer, model_validator

from ergon_core.api._serialization import TaskDefinitionJson, import_component_subclass


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
            return cls.from_definition(data)
        return handler(data)

    @classmethod
    def from_definition(cls, toolkit_json: TaskDefinitionJson) -> "Toolkit":
        """Reconstruct a Toolkit subclass from ``_type``-discriminated JSON."""

        toolkit_type = toolkit_json.get("_type")
        if not isinstance(toolkit_type, str):
            raise ValueError(
                f"Toolkit snapshot is missing the required `_type` discriminator "
                f"(got {type(toolkit_type).__name__}). Every persisted toolkit "
                f"must carry `_type`."
            )
        ToolkitCls = import_component_subclass(toolkit_type, Toolkit, kind="Toolkit")
        return cast("Toolkit", ToolkitCls.model_validate(toolkit_json))

    @abstractmethod
    def tools(self, sandbox: Any, task: Any) -> list:  # slopcop: ignore[no-typing-any]
        """Build live pydantic_ai Tool instances bound to a sandbox + task."""
