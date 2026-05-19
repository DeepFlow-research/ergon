"""Prefix-based model target resolution for built-in PydanticAI backends."""

import logging
from collections.abc import Callable
from dataclasses import dataclass

import pydantic_ai.models
from ergon_core.core.shared.json_types import JsonObject
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
_DEFAULT_MODEL_TARGET = "openai:gpt-4o"


class ResolvedModel(BaseModel):
    """A resolved model target with backend metadata."""

    model_config = {"frozen": True, "arbitrary_types_allowed": True}

    model: pydantic_ai.models.Model | str
    policy_version: str | None = None
    supports_logprobs: bool = False
    capture_model_settings: JsonObject | None = None


@dataclass(frozen=True)
class _ModelTarget:
    raw: str
    prefix: str
    name: str

    @classmethod
    def parse(cls, model_target: str | None) -> "_ModelTarget":
        raw = model_target or _DEFAULT_MODEL_TARGET
        prefix, separator, name = raw.partition(":")
        if not separator:
            return cls(raw=raw, prefix="", name=raw)
        return cls(raw=raw, prefix=prefix, name=name)


_BackendResolver = Callable[..., ResolvedModel]
_CaptureSettingsResolver = Callable[["_ModelTarget", bool], JsonObject | None]

_BACKEND_REGISTRY: dict[str, _BackendResolver] = {}


def register_model_backend(prefix: str, resolver: _BackendResolver) -> None:
    """Register a model backend resolver for a given target prefix."""
    _BACKEND_REGISTRY[prefix] = resolver


def registered_model_backend_prefixes() -> set[str]:
    """Return the model backend prefixes registered in this process."""
    return set(_BACKEND_REGISTRY)


def capture_model_settings_for(
    model_target: str | None,
    *,
    supports_logprobs: bool = False,
) -> JsonObject | None:
    """Return PydanticAI model settings for richer transcript capture."""
    target = _ModelTarget.parse(model_target)
    resolver = _CAPTURE_SETTINGS_BY_PREFIX.get(target.prefix)
    if resolver is None:
        return None
    return resolver(target, supports_logprobs)


def _vllm_capture_settings(
    _target: _ModelTarget,
    supports_logprobs: bool,
) -> JsonObject | None:
    if supports_logprobs:
        return dict(_OPENAI_COMPAT_LOGPROB_SETTINGS)
    return None


def _anthropic_capture_settings(
    target: _ModelTarget,
    _supports_logprobs: bool,
) -> JsonObject:
    if target.name.lower().startswith("claude-opus-4.7"):
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


def _openrouter_capture_settings(
    target: _ModelTarget,
    _supports_logprobs: bool,
) -> JsonObject:
    return {
        "openrouter_reasoning": dict(_openrouter_reasoning_settings_for(target.name)),
    }


def _openai_responses_capture_settings(
    _target: _ModelTarget,
    _supports_logprobs: bool,
) -> JsonObject:
    return {
        "openai_reasoning_effort": "medium",
        "openai_reasoning_summary": "detailed",
    }


def _google_capture_settings(
    _target: _ModelTarget,
    _supports_logprobs: bool,
) -> JsonObject:
    return {
        "gemini_thinking_config": {
            "include_thoughts": True,
        }
    }


def _openrouter_reasoning_settings_for(model_name: str) -> OpenRouterReasoning:
    model_name = model_name.lower()
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


_CAPTURE_SETTINGS_BY_PREFIX: dict[str, _CaptureSettingsResolver] = {
    "vllm": _vllm_capture_settings,
    "anthropic": _anthropic_capture_settings,
    "openrouter": _openrouter_capture_settings,
    "openai-responses": _openai_responses_capture_settings,
    "google": _google_capture_settings,
}


def _with_capture_settings(target: _ModelTarget, resolved: ResolvedModel) -> ResolvedModel:
    settings = capture_model_settings_for(
        target.raw,
        supports_logprobs=resolved.supports_logprobs,
    )
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
    target = _ModelTarget.parse(model_target)

    resolver = _BACKEND_REGISTRY.get(target.prefix)
    if resolver is not None:
        return _with_capture_settings(
            target,
            resolver(
                target.raw,
                model_name=model_name,
                policy_version=policy_version,
                api_key=api_key,
            ),
        )

    return _with_capture_settings(target, ResolvedModel(model=target.raw, supports_logprobs=False))
