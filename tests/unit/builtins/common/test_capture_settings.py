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


def test_anthropic_opus_47_uses_adaptive_summarized_thinking() -> None:
    assert capture_model_settings_for("anthropic:claude-opus-4.7") == {
        "anthropic_thinking": {"type": "adaptive", "display": "summarized"},
        "anthropic_effort": "medium",
    }


def test_openrouter_includes_reasoning() -> None:
    assert capture_model_settings_for("openrouter:anthropic/claude-sonnet-4.6") == {
        "openrouter_reasoning": {"max_tokens": 4096, "exclude": False},
    }


def test_openrouter_opus_uses_larger_reasoning_budget() -> None:
    assert capture_model_settings_for("openrouter:anthropic/claude-opus-4.7") == {
        "openrouter_reasoning": {"max_tokens": 8192, "exclude": False},
    }


def test_openrouter_openai_uses_reasoning_effort() -> None:
    assert capture_model_settings_for("openrouter:openai/gpt-5.1") == {
        "openrouter_reasoning": {"effort": "medium", "exclude": False},
    }


def test_openai_responses_uses_detailed_reasoning_summary() -> None:
    assert capture_model_settings_for("openai-responses:gpt-5.5-pro") == {
        "openai_reasoning_effort": "medium",
        "openai_reasoning_summary": "detailed",
    }


def test_google_includes_thoughts() -> None:
    assert capture_model_settings_for("google:gemini-2.5-pro") == {
        "gemini_thinking_config": {"include_thoughts": True},
    }


def test_unknown_provider_without_capture_returns_none() -> None:
    assert capture_model_settings_for("openai:gpt-4o") is None
