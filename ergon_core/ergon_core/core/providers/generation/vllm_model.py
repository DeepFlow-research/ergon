"""Model resolution and vLLM-specific PydanticAI model creation.

Provides ``resolve_model_target`` as the single entry point for
resolving ``model_target`` strings (e.g. ``"openai:gpt-4o"`` or
``"vllm:http://localhost:8000"``) to a PydanticAI-compatible model.
"""

import json as _json
import logging
import urllib.request

import pydantic_ai.models
from pydantic import BaseModel
from pydantic_ai.models.openai import OpenAIChatModel  # ty: ignore[unresolved-import]
from pydantic_ai.providers.openai import OpenAIProvider

logger = logging.getLogger(__name__)


class ResolvedModel(BaseModel):
    """A resolved model target with optional policy provenance metadata.

    Workers pass ``.model`` to ``Agent(model=...)``, and read
    ``.policy_version`` for metadata on the WorkerOutput.
    """

    model_config = {"frozen": True, "arbitrary_types_allowed": True}

    model: pydantic_ai.models.Model | str
    policy_version: str | None = None


def resolve_model_target(
    model_target: str | None,
    *,
    model_name: str | None = None,
    policy_version: str | None = None,
    api_key: str | None = None,
) -> ResolvedModel:
    """Resolve a ``model_target`` string to a PydanticAI-compatible model.

    For ``vllm:http://...`` targets, creates an ``OpenAIChatModel``
    backed by the vLLM endpoint.  For everything else, returns the
    string for PydanticAI's ``infer_model`` to resolve.

    The vLLM OpenAI-compatible API requires the actual HuggingFace model
    name as the ``model`` parameter.  Pass it via *model_name*; if not
    provided, the endpoint URL is queried at ``/v1/models`` to discover
    the served model.
    """
    target = model_target or "openai:gpt-4o"

    if target.startswith("vllm:"):
        endpoint = target[5:].rstrip("/")
        resolved_name = model_name or _discover_vllm_model_name(endpoint)
        provider = OpenAIProvider(
            base_url=f"{endpoint}/v1",
            api_key=api_key or "not-needed",
        )
        model = OpenAIChatModel(model_name=resolved_name, provider=provider)
        logger.info(
            "Resolved vLLM model: endpoint=%s model_name=%s policy_version=%s",
            endpoint,
            resolved_name,
            policy_version,
        )
        return ResolvedModel(model=model, policy_version=policy_version)

    return ResolvedModel(model=target, policy_version=None)


def _discover_vllm_model_name(endpoint: str) -> str:
    """Query ``/v1/models`` to discover the served model name.

    Falls back to ``"default"`` if the endpoint is unreachable (e.g.
    during test setup before vLLM is running).
    """
    url = f"{endpoint}/v1/models"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            body = _json.loads(resp.read())
        models = body.get("data", [])
        if models:
            name = models[0].get("id", "default")
            logger.info("Discovered vLLM model name: %s", name)
            return name
    except Exception:  # slopcop: ignore[no-broad-except]
        logger.warning("Could not discover vLLM model name from %s, using 'default'", url)
    return "default"
