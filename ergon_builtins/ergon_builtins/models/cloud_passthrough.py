"""Cloud passthrough: resolves ``openai:``, ``anthropic:``, etc. by passing through to PydanticAI."""

from h_arcane.core.providers.generation.model_resolution import ResolvedModel


def resolve_cloud(
    target: str,
    *,
    model_name: str | None = None,
    policy_version: str | None = None,
    api_key: str | None = None,
) -> ResolvedModel:
    """Pass cloud model targets through to PydanticAI's infer_model."""
    return ResolvedModel(model=target, supports_logprobs=False)
