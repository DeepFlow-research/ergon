"""Tests for the ``openrouter:`` model-target backend.

We route CI and cost-sensitive local runs through OpenRouter.  The
backend lives in ``ergon_builtins.models.openrouter_backend`` and gets
registered under the ``openrouter`` prefix in ``registry_core``.  These
tests pin both facts so we don't silently regress back to the old
``OPENAI_BASE_URL`` hijack.
"""

import pytest
from pydantic_ai.models.openai import OpenAIModel


class TestOpenRouterBackendRegistration:
    """Verify the ``openrouter`` prefix resolves to the OpenRouter resolver."""

    def test_openrouter_prefix_registered(self):
        from ergon_builtins.registry_core import MODEL_BACKENDS
        from ergon_builtins.models.openrouter_backend import resolve_openrouter

        assert "openrouter" in MODEL_BACKENDS
        assert MODEL_BACKENDS["openrouter"] is resolve_openrouter


class TestResolveOpenRouter:
    """Verify the resolver builds a pydantic-ai model backed by OpenRouter."""

    def test_resolve_builds_openai_model(self):
        """``openrouter:<provider>/<model>`` → ``OpenAIModel(provider='openrouter')``.

        We don't need an ``OPENROUTER_API_KEY`` for this path because
        passing ``api_key=...`` bypasses the env lookup.  That's the
        ergonomic seam that lets callers override provider keys per-run.
        """
        from ergon_builtins.models.openrouter_backend import resolve_openrouter

        resolved = resolve_openrouter(
            "openrouter:openai/gpt-4o-mini",
            api_key="sk-or-v1-test-only-do-not-ship",
        )

        assert isinstance(resolved.model, OpenAIModel)
        # pydantic-ai normalises the inner model name on the Model object.
        assert "gpt-4o-mini" in resolved.model.model_name
        assert resolved.supports_logprobs is False

    def test_resolve_rejects_wrong_prefix(self):
        """A bare ``openai:`` target is out of scope for this resolver."""
        from ergon_builtins.models.openrouter_backend import resolve_openrouter

        with pytest.raises(ValueError, match="openrouter"):
            resolve_openrouter("openai:gpt-4o-mini", api_key="x")

    def test_resolve_rejects_empty_inner(self):
        from ergon_builtins.models.openrouter_backend import resolve_openrouter

        with pytest.raises(ValueError, match="openrouter"):
            resolve_openrouter("openrouter:", api_key="x")


class TestDispatchThroughResolveModelTarget:
    """End-to-end: the core dispatcher routes ``openrouter:`` to us."""

    def test_resolve_model_target_dispatches_to_openrouter(self):
        # Importing the registry runs ``register_model_backend`` for every
        # prefix, which is the wiring we actually want to test here.
        import ergon_builtins.registry  # noqa: F401  — side-effect import
        from ergon_core.core.providers.generation.model_resolution import (
            resolve_model_target,
        )

        resolved = resolve_model_target(
            "openrouter:openai/gpt-4o-mini",
            api_key="sk-or-v1-test-only-do-not-ship",
        )
        assert isinstance(resolved.model, OpenAIModel)
