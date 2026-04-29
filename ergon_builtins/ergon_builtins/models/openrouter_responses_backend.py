"""OpenAI Responses-compatible models routed through OpenRouter billing."""

import logging

from ergon_core.core.shared.settings import settings
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider

from ergon_builtins.models.resolution import ResolvedModel

logger = logging.getLogger(__name__)


def resolve_openrouter_responses(
    target: str,
    *,
    model_name: str | None = None,
    policy_version: str | None = None,
    api_key: str | None = None,
) -> ResolvedModel:
    """Resolve ``openai-responses:model`` through OpenRouter's Responses endpoint."""
    resolved_name = model_name or _openrouter_model_name(target.removeprefix("openai-responses:"))
    provider = OpenAIProvider(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key or settings.openrouter_api_key,
    )
    model = OpenAIResponsesModel(model_name=resolved_name, provider=provider)
    logger.info("Resolved OpenRouter Responses model: model_name=%s", resolved_name)
    return ResolvedModel(model=model, policy_version=policy_version, supports_logprobs=False)


def _openrouter_model_name(name: str) -> str:
    return name if "/" in name else f"openai/{name}"
