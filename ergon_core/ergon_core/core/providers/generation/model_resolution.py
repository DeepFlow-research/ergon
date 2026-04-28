"""Prefix-based model target resolution."""

import pydantic_ai.models
from pydantic import BaseModel


class ResolvedModel(BaseModel):
    """A resolved model target with backend metadata.

    Workers pass ``.model`` to ``Agent(model=...)``, read
    ``.policy_version`` for provenance metadata, and check
    ``.supports_logprobs`` to decide whether to expect per-token
    logprob data in the response.
    """

    model_config = {"frozen": True, "arbitrary_types_allowed": True}

    model: pydantic_ai.models.Model | str
    policy_version: str | None = None
    supports_logprobs: bool = False


def resolve_model_target(
    model_target: str | None,
    *,
    model_name: str | None = None,
    policy_version: str | None = None,
    api_key: str | None = None,
) -> ResolvedModel:
    """Resolve a ``model_target`` string to a PydanticAI-compatible model.

    Cloud provider targets (``openai:*``, ``anthropic:*``, ``google:*``)
    intentionally resolve to OpenRouter-hosted models. Direct cloud provider
    API access is not part of Ergon's model-target grammar.
    """

    target = model_target or "openai:gpt-4o"
    prefix = target.split(":", 1)[0] if ":" in target else ""

    if prefix == "vllm":
        from ergon_core.core.providers.generation.openai_compatible import (  # slopcop: ignore[guarded-function-import] -- reason: avoid import cycle; provider modules import ResolvedModel
            resolve_vllm,
        )

        return resolve_vllm(
            target, model_name=model_name, policy_version=policy_version, api_key=api_key
        )

    if prefix == "openai-compatible":
        from ergon_core.core.providers.generation.openai_compatible import (  # slopcop: ignore[guarded-function-import] -- reason: avoid import cycle; provider modules import ResolvedModel
            resolve_openai_compatible,
        )

        return resolve_openai_compatible(
            target, model_name=model_name, policy_version=policy_version, api_key=api_key
        )

    if prefix in {"openai", "anthropic", "google"}:
        from ergon_core.core.providers.generation.openrouter import (  # slopcop: ignore[guarded-function-import] -- reason: avoid import cycle; provider modules import ResolvedModel
            resolve_cloud_via_openrouter,
        )

        return resolve_cloud_via_openrouter(
            target, model_name=model_name, policy_version=policy_version, api_key=api_key
        )

    if prefix == "openrouter":
        from ergon_core.core.providers.generation.openrouter import (  # slopcop: ignore[guarded-function-import] -- reason: avoid import cycle; provider modules import ResolvedModel
            resolve_openrouter_alias,
        )

        return resolve_openrouter_alias(
            target, model_name=model_name, policy_version=policy_version, api_key=api_key
        )

    raise ValueError(f"Unsupported model target: {target!r}")
