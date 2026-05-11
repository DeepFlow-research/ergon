"""Definition JSON helpers for public authoring models."""

from importlib import import_module
from typing import Any, TypeVar

from pydantic import BaseModel

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


def is_definition(value: object) -> bool:
    """Return true for persisted authoring definition dictionaries."""
    return isinstance(value, dict) and "_type" in value


def from_definition_dict(definition: dict[str, Any]) -> Any:  # slopcop: ignore[no-typing-any]
    """Inflate a `_type`-tagged definition dictionary into its concrete model."""
    model_cls = import_component_string(definition["_type"])
    data = dict(definition)
    data.pop("_type", None)
    return model_cls.model_validate(data)


def to_definition_dict(model: BaseModel) -> dict[str, Any]:  # slopcop: ignore[no-typing-any]
    """Serialize a Pydantic authoring object with an explicit type discriminator."""
    data = _definition_model_dump(model)
    data["_type"] = component_path(type(model))
    return data


def _definition_value(value: Any) -> Any:  # slopcop: ignore[no-typing-any]
    to_definition = getattr(value, "to_definition", None)
    if callable(to_definition):
        return to_definition()
    if isinstance(value, BaseModel):
        return _definition_model_dump(value)
    if isinstance(value, tuple | list):
        return [_definition_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _definition_value(item) for key, item in value.items()}
    return value


def _definition_model_dump(model: BaseModel) -> dict[str, Any]:  # slopcop: ignore[no-typing-any]
    data = model.model_dump(mode="json")
    for field_name in type(model).model_fields:
        if field_name in data:
            data[field_name] = _definition_value(getattr(model, field_name))
    return data
