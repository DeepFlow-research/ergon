from ergon_builtins.models.resolution import resolve_model_target
from ergon_builtins.registry import register_builtins

register_builtins()


def test_openrouter_target_resolves_to_openrouter_provider_model() -> None:
    resolved = resolve_model_target("openrouter:anthropic/claude-sonnet-4.6")

    assert type(resolved.model).__name__ == "OpenRouterModel"
    assert resolved.model.model_name == "anthropic/claude-sonnet-4.6"
    assert resolved.model.system == "openrouter"
    assert resolved.supports_logprobs is False
    assert resolved.capture_model_settings == {
        "openrouter_reasoning": {"max_tokens": 4096, "exclude": False},
    }


def test_openai_responses_target_routes_through_openrouter_responses() -> None:
    resolved = resolve_model_target("openai-responses:gpt-5.5-pro")

    assert type(resolved.model).__name__ == "OpenAIResponsesModel"
    assert resolved.model.model_name == "openai/gpt-5.5-pro"
    assert resolved.supports_logprobs is False
    assert resolved.capture_model_settings == {
        "openai_reasoning_effort": "medium",
        "openai_reasoning_summary": "detailed",
    }
