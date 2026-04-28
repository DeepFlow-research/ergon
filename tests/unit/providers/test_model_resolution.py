import pytest

from ergon_core.core.providers.generation.model_resolution import resolve_model_target


def test_cloud_provider_targets_resolve_to_openrouter_provider() -> None:
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openrouter import OpenRouterProvider

    resolved = resolve_model_target("openai:gpt-4o", api_key="test-openrouter-key")

    assert isinstance(resolved.model, OpenAIChatModel)
    assert isinstance(resolved.model._provider, OpenRouterProvider)
    assert resolved.model.model_name == "openai/gpt-4o"
    assert resolved.model.system == "openrouter"
    assert resolved.supports_logprobs is False


def test_anthropic_target_resolves_to_openrouter_namespace() -> None:
    from pydantic_ai.models.openai import OpenAIChatModel

    resolved = resolve_model_target("anthropic:claude-sonnet-4.6", api_key="test-openrouter-key")

    assert isinstance(resolved.model, OpenAIChatModel)
    assert resolved.model.model_name == "anthropic/claude-sonnet-4.6"


def test_vllm_endpoint_target_resolves_to_openai_compatible_model() -> None:
    from pydantic_ai.models.openai import OpenAIChatModel

    resolved = resolve_model_target("vllm:http://localhost:8000#served-model")

    assert isinstance(resolved.model, OpenAIChatModel)
    assert resolved.model.model_name == "served-model"
    assert resolved.supports_logprobs is True


def test_openai_compatible_target_requires_model_name() -> None:
    with pytest.raises(ValueError, match="model name"):
        resolve_model_target("openai-compatible:http://localhost:11434/v1")


def test_unknown_model_target_prefix_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unsupported model target"):
        resolve_model_target("mystery:model")
