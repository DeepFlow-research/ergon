"""Components that require the [local-models] capability (torch + transformers).

Eager, fully-typed imports.  This module will fail to import if torch/
transformers/outlines are not installed — that's by design.  The composition
layer in registry.py handles the ImportError gracefully.
"""

from collections.abc import Callable

from ergon_core.core.providers.generation.model_resolution import ResolvedModel

from ergon_builtins.models.transformers_backend import resolve_transformers

MODEL_BACKENDS: dict[str, Callable[..., ResolvedModel]] = {
    "transformers": resolve_transformers,
}
