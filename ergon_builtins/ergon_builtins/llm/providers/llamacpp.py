"""llama.cpp backend alias for local OpenAI-compatible servers."""

from ergon_builtins.llm.providers.openai_compatible import resolve_openai_compatible_target
from ergon_builtins.llm.resolution import ResolvedModel


def resolve_llamacpp(
    target: str,
    *,
    model_name: str | None = None,
    policy_version: str | None = None,
    api_key: str | None = None,
) -> ResolvedModel:
    """Resolve a ``llamacpp:http://...`` target to a PydanticAI model."""
    return resolve_openai_compatible_target(
        target,
        model_name=model_name,
        policy_version=policy_version,
        api_key=api_key,
        backend_label="llama.cpp",
    )


__all__ = ["resolve_llamacpp"]
