"""Generation provider helpers for model-specific integrations."""

from h_arcane.core.providers.generation.model_resolution import (
    ResolvedModel,
    register_model_backend,
    resolve_model_target,
)

__all__ = ["ResolvedModel", "register_model_backend", "resolve_model_target"]
