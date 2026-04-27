"""Prefix-based model target resolution for built-in PydanticAI backends."""

import logging
from collections.abc import Callable

from ergon_core.api.json_types import JsonObject
import pydantic_ai.models
from pydantic import BaseModel

logger = logging.getLogger(__name__)

_ANTHROPIC_THINKING_BUDGET_TOKENS = 1024
_OPENAI_COMPAT_LOGPROB_SETTINGS: JsonObject = {
    "openai_logprobs": True,
    "openai_top_logprobs": 1,
}


class ResolvedModel(BaseModel):
    """A resolved model target with backend metadata."""

    model_config = {"frozen": True, "arbitrary_types_allowed": True}

    model: pydantic_ai.models.Model | str
    policy_version: str | None = None
    supports_logprobs: bool = False
    capture_model_settings: JsonObject | None = None


_BACKEND_REGISTRY: dict[str, Callable[..., ResolvedModel]] = {}


def register_model_backend(prefix: str, resolver: Callable[..., ResolvedModel]) -> None:
    """Register a model backend resolver for a given target prefix."""
    _BACKEND_REGISTRY[prefix] = resolver


def _target_prefix(model_target: str | None) -> str:
    target = model_target or ""
    return target.split(":", 1)[0] if ":" in target else ""


def capture_model_settings_for(
    model_target: str | None,
    *,
    supports_logprobs: bool = False,
) -> JsonObject | None:
    """Return PydanticAI model settings for richer transcript capture."""
    prefix = _target_prefix(model_target)

    if prefix == "vllm" and supports_logprobs:
        return dict(_OPENAI_COMPAT_LOGPROB_SETTINGS)

    if prefix == "anthropic":
        return {
            "anthropic_thinking": {
                "type": "enabled",
                "budget_tokens": _ANTHROPIC_THINKING_BUDGET_TOKENS,
            }
        }

    if prefix == "openrouter":
        return {
            "openrouter_reasoning": {
                "enabled": True,
                "exclude": False,
            }
        }

    if prefix == "google":
        return {
            "gemini_thinking_config": {
                "include_thoughts": True,
            }
        }

    return None


def _with_capture_settings(target: str, resolved: ResolvedModel) -> ResolvedModel:
    settings = capture_model_settings_for(target, supports_logprobs=resolved.supports_logprobs)
    if resolved.capture_model_settings == settings:
        return resolved
    return resolved.model_copy(update={"capture_model_settings": settings})


def resolve_model_target(
    model_target: str | None,
    *,
    model_name: str | None = None,
    policy_version: str | None = None,
    api_key: str | None = None,
) -> ResolvedModel:
    """Resolve a model target string to a PydanticAI-compatible model."""
    target = model_target or "openai:gpt-4o"
    prefix = _target_prefix(target)

    resolver = _BACKEND_REGISTRY.get(prefix)
    if resolver is not None:
        return _with_capture_settings(
            target,
            resolver(
                target,
                model_name=model_name,
                policy_version=policy_version,
                api_key=api_key,
            ),
        )

    return _with_capture_settings(target, ResolvedModel(model=target, supports_logprobs=False))
