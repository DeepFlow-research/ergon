"""Definition JSON serialization for authoring models."""

from collections.abc import Mapping
from importlib import import_module
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

DefinitionData = dict[str, Any]  # slopcop: ignore[no-typing-any]


class DefinitionEnvelope(BaseModel):
    """Typed wrapper for the discriminator stored with persisted definitions."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    type_path: str = Field(alias="_type")

    @property
    def body(self) -> DefinitionData:
        return dict(self.model_extra or {})


def has_definition_type(value: object) -> bool:
    """Return true for persisted authoring definition payloads."""
    return isinstance(value, Mapping) and isinstance(value.get("_type"), str)


def inflate_definition(definition: Mapping[str, Any]) -> Any:  # slopcop: ignore[no-typing-any]
    """Inflate a `_type`-tagged definition payload into its concrete model."""
    envelope = DefinitionEnvelope.model_validate(definition)
    model_cls = import_model_type(envelope.type_path)
    return model_cls.model_validate(envelope.body)


def serialize_definition(model: BaseModel) -> DefinitionData:
    """Serialize a Pydantic authoring object with an explicit type discriminator."""
    data = _serialize_model_fields(model)
    data["_type"] = model_type_path(type(model))
    return data


def import_model_type(path: str) -> type[Any]:  # slopcop: ignore[no-typing-any]
    """Import a model class from a `module:qualname` discriminator."""
    module_name, separator, qualname = path.partition(":")
    if not separator:
        module_name, _, qualname = path.rpartition(".")
    if not module_name or not qualname:
        raise ValueError(f"Invalid component path {path!r}")

    component: Any = import_module(module_name)  # slopcop: ignore[no-typing-any]
    for part in qualname.split("."):
        component = getattr(component, part)
    return component


def model_type_path(component_type: type[object]) -> str:
    """Return the stable import path used in `_type` discriminators."""
    return f"{component_type.__module__}:{component_type.__qualname__}"


def _serialize_value(value: Any) -> Any:  # slopcop: ignore[no-typing-any]
    to_definition = getattr(value, "to_definition", None)
    if callable(to_definition):
        return to_definition()
    if isinstance(value, BaseModel):
        return _serialize_model_fields(value)
    if isinstance(value, tuple | list):
        return [_serialize_value(item) for item in value]
    if isinstance(value, Mapping):
        return {key: _serialize_value(item) for key, item in value.items()}
    return value


def _serialize_model_fields(model: BaseModel) -> DefinitionData:
    data = model.model_dump(mode="json")
    for field_name in type(model).model_fields:
        if field_name in data:
            data[field_name] = _serialize_value(getattr(model, field_name))
    return data

