"""vLLM backend compatibility alias for local OpenAI-compatible servers."""

from ergon_builtins.llm.providers.openai_compatible import (
    discover_model_name as _discover_model_name,
)
from ergon_builtins.llm.providers.openai_compatible import resolve_openai_compatible_target
from ergon_builtins.llm.resolution import ResolvedModel


def resolve_vllm(
    target: str,
    *,
    model_name: str | None = None,
    policy_version: str | None = None,
    api_key: str | None = None,
) -> ResolvedModel:
    """Resolve a ``vllm:http://...`` target to a PydanticAI model."""
    return resolve_openai_compatible_target(
        target,
        model_name=model_name,
        policy_version=policy_version,
        api_key=api_key,
        backend_label="vLLM",
    )


__all__ = ["_discover_model_name", "resolve_vllm"]
