"""Framework-internal helpers for v2 component serialization.

Lives outside the public-API class files (``task.py``, ``worker.py``,
``sandbox.py``) so authors reading those files see the class
definitions first, not the framework's discriminator-resolution
machinery. Re-exported through each component class via
``from_definition`` classmethods — authors never call the helpers
here directly.
"""

from importlib import import_module
from typing import Any, TypeVar, cast

from pydantic import JsonValue


type TaskDefinitionJson = dict[str, JsonValue]
"""Serialized form of a Task / Worker / Sandbox / Criterion / etc —
``_type``-discriminated JSON written to ``run_graph_nodes.task_json``
and the matching definition columns. Field names are NOT enforced by
this type (the discriminator dispatch in ``from_definition`` does
that); the value side IS typed via pydantic's ``JsonValue``, so
accidentally stuffing a ``datetime`` or ``UUID`` object into the
snapshot fails at typecheck time instead of at JSON-serialization
time. The alias is the named boundary every ``from_definition``
classmethod accepts."""


ComponentClass = type[object]


def component_type_path(component: object) -> str:
    """Return the importable ``module:qualname`` discriminator for a component."""

    component_type = type(component)
    qualname = component_type.__qualname__
    if "[" in qualname or "]" in qualname:
        component_name = component_type.__name__.split("[", 1)[0]
        raise ValueError(
            f"{component_name} snapshot cannot be persisted from a parametrized generic; "
            f"got {qualname!r}. Persisted {component_name} snapshots must use a "
            f"concrete {component_name} subclass."
        )
    return f"{component_type.__module__}:{qualname}"


def inject_type_discriminator(
    payload: dict[str, Any],
    component: object,
) -> dict[str, Any]:
    """Add ``_type`` to an existing serialized payload and return it."""

    payload["_type"] = component_type_path(component)
    return payload


def import_component(path: str) -> ComponentClass:
    """Resolve a ``module:qualname`` string to a class.

    Used by every ``<Component>.from_definition`` classmethod to
    dispatch on the ``_type`` discriminator. Raises ``ValueError`` on
    malformed paths and ``TypeError`` if the resolved object is not a
    class.
    """

    module_name, _, qualname = path.partition(":")
    if not module_name or not qualname:
        raise ValueError(f"Component _type must be 'module:qualname', got {path!r}")
    obj: Any = import_module(module_name)
    for part in qualname.split("."):
        # typing: dynamic qualname walk — `part` is a user-controlled discriminator component.
        obj = getattr(obj, part)
    if not isinstance(obj, type):
        raise TypeError(f"Component _type {path!r} did not resolve to a class")
    return cast("ComponentClass", obj)


T = TypeVar("T")


def import_component_subclass(
    path: str,
    expected_base: type[T],
    *,
    kind: str,
) -> type[T]:
    """Resolve ``path`` and verify it names a subclass of ``expected_base``."""

    imported = import_component(path)
    if not issubclass(imported, expected_base):
        raise TypeError(
            f"{kind} _type {path!r} did not resolve to a {expected_base.__name__} subclass"
        )
    return cast("type[T]", imported)
