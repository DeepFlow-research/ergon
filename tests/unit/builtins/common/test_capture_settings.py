from ergon_builtins.models.resolution import ResolvedModel, capture_model_settings_for


def _resolved(*, supports_logprobs: bool = False) -> ResolvedModel:
    return ResolvedModel(
        model="dummy",
        supports_logprobs=supports_logprobs,
        capture_model_settings=capture_model_settings_for(
            "vllm:http://localhost:8000" if supports_logprobs else "openai:gpt-4o",
            supports_logprobs=supports_logprobs,
        ),
    )


def test_vllm_enables_logprobs() -> None:
    assert _resolved(supports_logprobs=True).capture_model_settings == {
        "openai_logprobs": True,
        "openai_top_logprobs": 1,
    }


def test_anthropic_enables_thinking() -> None:
    assert capture_model_settings_for("anthropic:claude-sonnet-4") == {
        "anthropic_thinking": {"type": "enabled", "budget_tokens": 1024},
    }


def test_openrouter_includes_reasoning() -> None:
    assert capture_model_settings_for("openrouter:anthropic/claude-sonnet-4.6") == {
        "openrouter_reasoning": {"enabled": True, "exclude": False},
    }


def test_google_includes_thoughts() -> None:
    assert capture_model_settings_for("google:gemini-2.5-pro") == {
        "gemini_thinking_config": {"include_thoughts": True},
    }


def test_unknown_provider_without_capture_returns_none() -> None:
    assert capture_model_settings_for("openai:gpt-4o") is None
