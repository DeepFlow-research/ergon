"""OpenAI-compatible local model target resolution."""

import json
import logging
import urllib.error
import urllib.request

from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from ergon_builtins.llm.resolution import ResolvedModel

logger = logging.getLogger(__name__)

_MODEL_DISCOVERY_TIMEOUT_SECONDS = 5


def resolve_openai_compatible(
    target: str,
    *,
    model_name: str | None = None,
    policy_version: str | None = None,
    api_key: str | None = None,
) -> ResolvedModel:
    """Resolve an ``openai-compatible:http://...`` target to a PydanticAI model."""
    return resolve_openai_compatible_target(
        target,
        model_name=model_name,
        policy_version=policy_version,
        api_key=api_key,
        backend_label="OpenAI-compatible",
    )


def resolve_openai_compatible_target(
    target: str,
    *,
    model_name: str | None = None,
    policy_version: str | None = None,
    api_key: str | None = None,
    backend_label: str,
) -> ResolvedModel:
    """Resolve any OpenAI-compatible endpoint target to a PydanticAI model."""
    endpoint, target_model_name = _endpoint_and_model_name(target)
    resolved_name = model_name or target_model_name or discover_model_name(endpoint, backend_label)
    provider = OpenAIProvider(
        base_url=f"{endpoint}/v1",
        api_key=api_key or "not-needed",
    )
    model = OpenAIChatModel(model_name=resolved_name, provider=provider)
    logger.info(
        "Resolved %s model: endpoint=%s model_name=%s policy_version=%s",
        backend_label,
        endpoint,
        resolved_name,
        policy_version,
    )
    return ResolvedModel(model=model, policy_version=policy_version, supports_logprobs=True)


def discover_model_name(endpoint: str, backend_label: str = "OpenAI-compatible") -> str:
    """Query ``/v1/models`` to discover the served model name."""
    url = f"{endpoint}/v1/models"
    try:
        with urllib.request.urlopen(url, timeout=_MODEL_DISCOVERY_TIMEOUT_SECONDS) as resp:
            body = json.loads(resp.read())
        if isinstance(body, dict):
            models = body.get("data", [])
            if isinstance(models, list):
                for model in models:
                    if not isinstance(model, dict):
                        continue
                    name = model.get("id")
                    if isinstance(name, str) and name:
                        logger.info("Discovered %s model name: %s", backend_label, name)
                        return name
    except (
        urllib.error.HTTPError,
        urllib.error.URLError,
        TimeoutError,
        OSError,
        json.JSONDecodeError,
    ):
        logger.warning(
            "Could not discover %s model name from %s, using 'default'",
            backend_label,
            url,
        )
    return "default"


def _endpoint_and_model_name(target: str) -> tuple[str, str | None]:
    _prefix, separator, name = target.partition(":")
    if not separator or not name:
        raise ValueError(f"OpenAI-compatible model target must include an endpoint: {target!r}")

    endpoint, _model_separator, target_model_name = name.partition("#")
    endpoint = endpoint.rstrip("/")
    if not endpoint:
        raise ValueError(f"OpenAI-compatible model target must include an endpoint: {target!r}")
    return endpoint, target_model_name or None


__all__ = [
    "discover_model_name",
    "resolve_openai_compatible",
    "resolve_openai_compatible_target",
]
