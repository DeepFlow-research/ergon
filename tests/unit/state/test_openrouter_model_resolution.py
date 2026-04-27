from ergon_builtins.models.resolution import resolve_model_target

# Importing the builtins registry registers production model backends.
import ergon_builtins.registry  # noqa: F401


def test_openrouter_target_resolves_to_openrouter_provider_model() -> None:
    resolved = resolve_model_target("openrouter:anthropic/claude-sonnet-4.6")

    assert type(resolved.model).__name__ == "OpenRouterModel"
    assert resolved.model.model_name == "anthropic/claude-sonnet-4.6"
    assert resolved.model.system == "openrouter"
    assert resolved.supports_logprobs is False
    assert resolved.capture_model_settings == {
        "openrouter_reasoning": {"enabled": True, "exclude": False},
    }
