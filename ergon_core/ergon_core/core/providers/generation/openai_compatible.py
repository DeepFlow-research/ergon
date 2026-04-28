"""OpenAI-compatible endpoint resolution for local and custom model servers."""

import json
import logging
import urllib.error
import urllib.request

from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from ergon_core.core.providers.generation.model_resolution import ResolvedModel

logger = logging.getLogger(__name__)


def resolve_openai_compatible(
    target: str,
    *,
    model_name: str | None = None,
    policy_version: str | None = None,
    api_key: str | None = None,
) -> ResolvedModel:
    """Resolve ``openai-compatible:<base-url>#<model>`` targets."""

    base_url, parsed_model_name = _split_endpoint_target(
        target,
        prefix="openai-compatible:",
        require_model_name=True,
    )
    resolved_name = model_name or parsed_model_name
    if resolved_name is None:
        raise ValueError("openai-compatible target requires a model name")
    provider = OpenAIProvider(base_url=base_url.rstrip("/"), api_key=api_key or "not-needed")
    model = OpenAIChatModel(model_name=resolved_name, provider=provider)
    return ResolvedModel(model=model, policy_version=policy_version, supports_logprobs=False)


def resolve_vllm(
    target: str,
    *,
    model_name: str | None = None,
    policy_version: str | None = None,
    api_key: str | None = None,
) -> ResolvedModel:
    """Resolve ``vllm:<endpoint>[#<model>]`` targets."""

    endpoint, parsed_model_name = _split_endpoint_target(
        target,
        prefix="vllm:",
        require_model_name=False,
    )
    endpoint = endpoint.rstrip("/")
    resolved_name = model_name or parsed_model_name or _discover_model_name(endpoint)
    provider = OpenAIProvider(base_url=f"{endpoint}/v1", api_key=api_key or "not-needed")
    model = OpenAIChatModel(model_name=resolved_name, provider=provider)
    logger.info(
        "Resolved vLLM model: endpoint=%s model_name=%s policy_version=%s",
        endpoint,
        resolved_name,
        policy_version,
    )
    return ResolvedModel(model=model, policy_version=policy_version, supports_logprobs=True)


def _split_endpoint_target(
    target: str,
    *,
    prefix: str,
    require_model_name: bool,
) -> tuple[str, str | None]:
    body = target.removeprefix(prefix)
    endpoint, separator, model_name = body.partition("#")
    if not endpoint:
        raise ValueError(f"{prefix}<base-url> target requires a base URL")
    if require_model_name and not (separator and model_name):
        raise ValueError(f"{prefix}<base-url>#<model-name> target requires a model name")
    return endpoint, model_name or None


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
