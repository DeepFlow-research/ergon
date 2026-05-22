"""Deprecated compatibility import for ``ergon_builtins.llm.resolution``."""

from ergon_builtins.llm.capture_settings import capture_model_settings_for
from ergon_builtins.llm.resolution import (
    ResolvedModel,
    register_model_backend,
    registered_model_backend_prefixes,
    resolve_model_target,
)

__all__ = [
    "ResolvedModel",
    "capture_model_settings_for",
    "register_model_backend",
    "registered_model_backend_prefixes",
    "resolve_model_target",
]
