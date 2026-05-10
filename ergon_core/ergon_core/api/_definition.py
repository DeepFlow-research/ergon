"""Definition JSON helpers for public authoring models."""

from importlib import import_module
from typing import Any, TypeVar

from pydantic import model_serializer

T = TypeVar("T")


def component_path(component_type: type[object]) -> str:
    """Return the stable import path used in `_type` discriminators."""
    return f"{component_type.__module__}:{component_type.__qualname__}"


def import_component_string(path: str) -> type[Any]:  # slopcop: ignore[no-typing-any]
    """Import a component class from a `module:qualname` discriminator."""
    module_name, separator, qualname = path.partition(":")
    if not separator:
        module_name, _, qualname = path.rpartition(".")
    if not module_name or not qualname:
        raise ValueError(f"Invalid component path {path!r}")

    component: Any = import_module(module_name)  # slopcop: ignore[no-typing-any]
    for part in qualname.split("."):
        component = getattr(component, part)
    return component


class DefinitionModelMixin:
    """Mixin that injects `_type` into pydantic model dumps."""

    @model_serializer(mode="wrap")
    def _serialize_with_type(self, serializer) -> dict[str, Any]:  # slopcop: ignore[no-typing-any]
        data = serializer(self)
        data["_type"] = component_path(type(self))
        return data
