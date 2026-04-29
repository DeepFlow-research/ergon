"""OpenRouter backend using PydanticAI's OpenRouter provider."""

import logging

from ergon_core.core.shared.settings import settings
from pydantic_ai.models.openrouter import OpenRouterModel, OpenRouterProvider

from ergon_builtins.models.resolution import ResolvedModel

logger = logging.getLogger(__name__)


def resolve_openrouter(
    target: str,
    *,
    model_name: str | None = None,
    policy_version: str | None = None,
    api_key: str | None = None,
) -> ResolvedModel:
    """Resolve ``openrouter:model-id`` to an OpenRouter-backed chat model."""
    resolved_name = model_name or target.removeprefix("openrouter:")
    provider = OpenRouterProvider(api_key=api_key or settings.openrouter_api_key or "unused")
    model = OpenRouterModel(model_name=resolved_name, provider=provider)
    logger.info("Resolved OpenRouter model: model_name=%s", resolved_name)
    return ResolvedModel(model=model, policy_version=policy_version, supports_logprobs=False)
