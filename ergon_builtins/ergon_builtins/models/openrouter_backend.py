"""OpenRouter backend: ``openrouter:<provider>/<model>`` → pydantic-ai.

We route through OpenRouter for CI (and anywhere else we want provider
diversification without juggling auth) using pydantic-ai's first-party
:class:`pydantic_ai.providers.openrouter.OpenRouterProvider` rather than
the historical hack of pointing the OpenAI client at OpenRouter's
base URL via ``OPENAI_BASE_URL``.

Why a dedicated prefix instead of reusing ``openai:``?

* Credential hygiene: the provider reads ``OPENROUTER_API_KEY``, which
  is a different secret from ``OPENAI_API_KEY``.  Reusing the
  ``openai:`` prefix + ``OPENAI_API_KEY`` meant any other code reading
  that env var thought it was talking to OpenAI directly.
* Accurate provenance: a model target of ``openrouter:openai/gpt-4o-mini``
  makes it obvious the traffic traverses OpenRouter; the telemetry
  ``policy_version`` downstream can key off the prefix.
* Drop-in swap: upstream routing (Anthropic → Gemini → OpenAI) happens
  by changing the model name after the prefix, never the key or URL.

Pattern mirrors ``deepflow-ml/core_v2/shared/models/configuration.py``
in FractalOS, which has been running the same posture in production.
"""

from pydantic_ai.models.openai import OpenAIModel

from ergon_core.core.providers.generation.model_resolution import ResolvedModel


def resolve_openrouter(
    target: str,
    *,
    model_name: str | None = None,  # noqa: ARG001  (registry contract; unused here)
    policy_version: str | None = None,
    api_key: str | None = None,
) -> ResolvedModel:
    """Resolve ``openrouter:<provider>/<model>`` to a pydantic-ai model.

    ``target`` comes in as the full ``openrouter:openai/gpt-4o-mini``
    string; we strip the ``openrouter:`` prefix and hand the rest to
    :class:`OpenAIModel` with ``provider='openrouter'``.  Under the hood
    that constructs an :class:`OpenRouterProvider`, which reads
    ``OPENROUTER_API_KEY`` from env (or uses ``api_key`` if provided)
    and wires an ``AsyncOpenAI`` client pointed at OpenRouter's
    OpenAI-compatible endpoint.  No ``OPENAI_BASE_URL`` hijack needed.
    """
    prefix, _, inner = target.partition(":")
    if prefix != "openrouter" or not inner:
        raise ValueError(
            f"resolve_openrouter expected target 'openrouter:<provider>/<model>', got {target!r}"
        )

    if api_key is not None:
        # Explicit override path: construct the provider ourselves so we
        # can pass the key directly instead of going via env.
        from pydantic_ai.providers.openrouter import OpenRouterProvider

        model = OpenAIModel(inner, provider=OpenRouterProvider(api_key=api_key))
    else:
        # Env path: pydantic-ai constructs an OpenRouterProvider that
        # reads OPENROUTER_API_KEY itself.  Keeps this module import-
        # order-safe because we never touch os.environ.
        model = OpenAIModel(inner, provider="openrouter")

    return ResolvedModel(
        model=model,
        policy_version=policy_version,
        supports_logprobs=False,
    )
