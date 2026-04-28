"""Prefix-based model target resolution for built-in PydanticAI backends."""

import logging
from collections.abc import Callable

import pydantic_ai.models
from ergon_core.core.json_types import JsonObject
from pydantic import BaseModel
from pydantic_ai.models.openrouter import OpenRouterReasoning

logger = logging.getLogger(__name__)

_ANTHROPIC_THINKING_BUDGET_TOKENS = 1024
_OPENROUTER_ANTHROPIC_SONNET_BUDGET_TOKENS = 4096
_OPENROUTER_ANTHROPIC_OPUS_BUDGET_TOKENS = 8192
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
        anthropic_model_name = (model_target or "").split(":", 1)[-1].lower()
        if anthropic_model_name.startswith("claude-opus-4.7"):
            return {
                "anthropic_thinking": {
                    "type": "adaptive",
                    "display": "summarized",
                },
                "anthropic_effort": "medium",
            }
        return {
            "anthropic_thinking": {
                "type": "enabled",
                "budget_tokens": _ANTHROPIC_THINKING_BUDGET_TOKENS,
            }
        }

    if prefix == "openrouter":
        return {
            "openrouter_reasoning": _openrouter_reasoning_settings_for(model_target),
        }

    if prefix == "openai-responses":
        return {
            "openai_reasoning_effort": "medium",
            "openai_reasoning_summary": "detailed",
        }

    if prefix == "google":
        return {
            "gemini_thinking_config": {
                "include_thoughts": True,
            }
        }

    return None


def _openrouter_reasoning_settings_for(model_target: str | None) -> OpenRouterReasoning:
    model_name = (model_target or "").split(":", 1)[-1].lower()
    if model_name.startswith("anthropic/claude-opus-4"):
        return OpenRouterReasoning(
            max_tokens=_OPENROUTER_ANTHROPIC_OPUS_BUDGET_TOKENS,
            exclude=False,
        )
    if model_name.startswith("anthropic/claude-sonnet-4"):
        return OpenRouterReasoning(
            max_tokens=_OPENROUTER_ANTHROPIC_SONNET_BUDGET_TOKENS,
            exclude=False,
        )
    if model_name.startswith("openai/gpt-5"):
        return OpenRouterReasoning(effort="medium", exclude=False)
    if model_name.startswith(("google/gemini-3", "moonshotai/kimi-k2")):
        return OpenRouterReasoning(effort="medium", exclude=False)
    return OpenRouterReasoning(enabled=True, exclude=False)


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
