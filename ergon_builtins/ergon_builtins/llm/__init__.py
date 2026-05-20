"""LLM target resolution and built-in backend registration."""

from ergon_builtins.llm.providers.llamacpp import resolve_llamacpp
from ergon_builtins.llm.providers.openai_compatible import resolve_openai_compatible
from ergon_builtins.llm.providers.vllm import resolve_vllm
from ergon_builtins.llm.resolution import (
    ResolvedModel,
    register_model_backend,
    registered_model_backend_prefixes,
    resolve_model_target,
)


def register_builtin_model_backends() -> None:
    """Register built-in model backends that ship with ``ergon_builtins``."""
    register_model_backend("openai-compatible", resolve_openai_compatible)
    register_model_backend("llamacpp", resolve_llamacpp)
    register_model_backend("vllm", resolve_vllm)


register_builtin_model_backends()


__all__ = [
    "ResolvedModel",
    "register_builtin_model_backends",
    "register_model_backend",
    "registered_model_backend_prefixes",
    "resolve_model_target",
]
