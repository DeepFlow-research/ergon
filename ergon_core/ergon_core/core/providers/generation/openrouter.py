"""OpenRouter-hosted cloud model resolution."""

from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openrouter import OpenRouterProvider

from ergon_core.core.providers.generation.model_resolution import ResolvedModel
from ergon_core.core.settings import settings

CLOUD_PROVIDER_PREFIXES = frozenset({"openai", "anthropic", "google"})


def resolve_cloud_via_openrouter(
    target: str,
    *,
    model_name: str | None = None,
    policy_version: str | None = None,
    api_key: str | None = None,
) -> ResolvedModel:
    """Resolve ``openai:*``, ``anthropic:*``, and ``google:*`` through OpenRouter."""

    provider_prefix, separator, provider_model_name = target.partition(":")
    if not separator or not provider_model_name:
        raise ValueError(f"Unsupported model target: {target!r}")
    if provider_prefix not in CLOUD_PROVIDER_PREFIXES:
        raise ValueError(f"Unsupported cloud provider target: {target!r}")

    openrouter_model_name = model_name or f"{provider_prefix}/{provider_model_name}"
    provider = _openrouter_provider(api_key)
    model = OpenAIChatModel(model_name=openrouter_model_name, provider=provider)
    return ResolvedModel(model=model, policy_version=policy_version, supports_logprobs=False)


def resolve_openrouter_alias(
    target: str,
    *,
    model_name: str | None = None,
    policy_version: str | None = None,
    api_key: str | None = None,
) -> ResolvedModel:
    """Resolve legacy ``openrouter:<provider>/<model>`` targets through OpenRouter."""

    provider_model_name = target.removeprefix("openrouter:")
    if not provider_model_name:
        raise ValueError("openrouter:<provider>/<model> target requires a model name")

    provider = _openrouter_provider(api_key)
    model = OpenAIChatModel(model_name=model_name or provider_model_name, provider=provider)
    return ResolvedModel(model=model, policy_version=policy_version, supports_logprobs=False)


def _openrouter_provider(api_key: str | None) -> OpenRouterProvider:
    resolved_api_key = api_key or settings.openrouter_api_key
    if resolved_api_key:
        return OpenRouterProvider(api_key=resolved_api_key)
    return OpenRouterProvider()
