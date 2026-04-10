"""vLLM backend: resolves ``vllm:http://...`` targets to OpenAI-compatible PydanticAI models."""

import json
import logging
import urllib.error
import urllib.request

from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from h_arcane.core.providers.generation.model_resolution import ResolvedModel

logger = logging.getLogger(__name__)


def resolve_vllm(
    target: str,
    *,
    model_name: str | None = None,
    policy_version: str | None = None,
    api_key: str | None = None,
) -> ResolvedModel:
    """Resolve a ``vllm:http://...`` target to a PydanticAI model."""
    endpoint = target[5:].rstrip("/")
    resolved_name = model_name or _discover_model_name(endpoint)
    provider = OpenAIProvider(
        base_url=f"{endpoint}/v1",
        api_key=api_key or "not-needed",
    )
    model = OpenAIChatModel(model_name=resolved_name, provider=provider)
    logger.info(
        "Resolved vLLM model: endpoint=%s model_name=%s policy_version=%s",
        endpoint, resolved_name, policy_version,
    )
    return ResolvedModel(model=model, policy_version=policy_version, supports_logprobs=True)


def _discover_model_name(endpoint: str) -> str:
    """Query ``/v1/models`` to discover the served model name."""
    url = f"{endpoint}/v1/models"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            body = json.loads(resp.read())
        models = body.get("data", [])
        if models:
            name = models[0].get("id", "default")
            logger.info("Discovered vLLM model name: %s", name)
            return name
    except (
        urllib.error.HTTPError,
        urllib.error.URLError,
        TimeoutError,
        OSError,
        json.JSONDecodeError,
    ):
        logger.warning("Could not discover vLLM model name from %s, using 'default'", url)
    return "default"
