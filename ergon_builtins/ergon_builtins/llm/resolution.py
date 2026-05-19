"""Prefix-based model target resolution for built-in PydanticAI backends."""

import logging
from collections.abc import Callable
from dataclasses import dataclass

import pydantic_ai.models
from ergon_core.core.shared.json_types import JsonObject
from pydantic import BaseModel

from ergon_builtins.llm.capture_settings import capture_model_settings_for

logger = logging.getLogger(__name__)

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

_BACKEND_REGISTRY: dict[str, _BackendResolver] = {}


def register_model_backend(prefix: str, resolver: _BackendResolver) -> None:
    """Register a model backend resolver for a given target prefix."""
    _BACKEND_REGISTRY[prefix] = resolver


def registered_model_backend_prefixes() -> set[str]:
    """Return the model backend prefixes registered in this process."""
    return set(_BACKEND_REGISTRY)


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
