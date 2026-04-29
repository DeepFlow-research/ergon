"""Components that require the [local-models] capability (torch + transformers).

Eager, fully-typed imports.  This module will fail to import if torch/
transformers/outlines are not installed — that's by design.  The composition
layer in registry.py handles the ImportError gracefully.
"""

from collections.abc import Callable

from ergon_builtins.models.resolution import ResolvedModel, register_model_backend
from ergon_builtins.models.transformers_backend import resolve_transformers

MODEL_BACKENDS: dict[str, Callable[..., ResolvedModel]] = {
    "transformers": resolve_transformers,
}


def register_local_model_builtins() -> None:
    """Register model backends that require local-model optional dependencies."""

    for prefix, resolver in MODEL_BACKENDS.items():
        register_model_backend(prefix, resolver)
