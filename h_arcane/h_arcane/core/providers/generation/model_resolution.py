"""Prefix-based model target resolution.

Dispatches ``model_target`` strings to the appropriate backend based on
their prefix (``vllm:``, ``transformers:``, ``openai:``, etc.).

Concrete backend implementations live in ``arcane_builtins.models``.
This module owns the contract (``ResolvedModel``) and the dispatch logic.
"""

import logging
from typing import Callable

import pydantic_ai.models
from pydantic import BaseModel

logger = logging.getLogger(__name__)


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


# Backend resolver registry: prefix -> callable
# Populated by arcane_builtins.registry at import time.
_BACKEND_REGISTRY: dict[str, Callable[..., ResolvedModel]] = {}


def register_model_backend(prefix: str, resolver: Callable[..., ResolvedModel]) -> None:
    """Register a model backend resolver for a given prefix."""
    _BACKEND_REGISTRY[prefix] = resolver


def resolve_model_target(
    model_target: str | None,
    *,
    model_name: str | None = None,
    policy_version: str | None = None,
    api_key: str | None = None,
) -> ResolvedModel:
    """Resolve a ``model_target`` string to a PydanticAI-compatible model.

    Dispatches by prefix to registered backends. Unrecognised prefixes
    are passed through to PydanticAI's ``infer_model``.
    """
    target = model_target or "openai:gpt-4o"

    prefix = target.split(":")[0] if ":" in target else ""

    resolver = _BACKEND_REGISTRY.get(prefix)
    if resolver is not None:
        return resolver(
            target,
            model_name=model_name,
            policy_version=policy_version,
            api_key=api_key,
        )

    return ResolvedModel(model=target, supports_logprobs=False)
