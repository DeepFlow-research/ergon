"""Unit tests for the ``stub:`` model backend.

Exercises ``resolve_stub`` directly and via the registry dispatch path to
pin the behaviour the real-LLM canary relies on: the ``stub:constant``
target resolves to a fixed, deterministic ``ResolvedModel`` instead of
silently falling through to PydanticAI.
"""

from ergon_builtins.models.stub_constant_backend import (
    STUB_CONSTANT_RESPONSE,
    resolve_stub,
)

# Importing ergon_builtins.registry triggers backend registration as a side
# effect; this is the same path the CLI takes at startup.
import ergon_builtins.registry  # noqa: F401
from ergon_core.core.providers.generation.model_resolution import (
    ResolvedModel,
    resolve_model_target,
)


def test_stub_constant_first_call_returns_expected_constant() -> None:
    resolved = resolve_stub("stub:constant")
    assert isinstance(resolved, ResolvedModel)
    assert resolved.model == STUB_CONSTANT_RESPONSE
    assert resolved.supports_logprobs is False


def test_stub_constant_second_call_is_deterministic() -> None:
    first = resolve_stub("stub:constant")
    second = resolve_stub("stub:constant")
    assert first.model == second.model == STUB_CONSTANT_RESPONSE
    assert first.supports_logprobs == second.supports_logprobs is False


def test_stub_backend_accepts_arbitrary_suffix_and_registry_dispatches() -> None:
    # Arbitrary suffixes are accepted (doesn't raise) and the prefix
    # dispatch goes through the registry all the way from a raw string.
    for target in ("stub:constant", "stub:anything", "stub:", "stub:with-kwargs"):
        direct = resolve_stub(target, model_name="ignored", policy_version="v0")
        via_registry = resolve_model_target(target)
        assert direct.model == STUB_CONSTANT_RESPONSE
        assert via_registry.model == STUB_CONSTANT_RESPONSE
