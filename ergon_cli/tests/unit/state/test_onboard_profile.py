"""Unit tests for OnboardProfile: required_keys() and required_extras()."""

import ergon_cli.domains.onboarding.profile as profile_module
from ergon_cli.domains.onboarding.profile import (
    GPUProvider,
    LLMProvider,
    OnboardProfile,
)


class TestRequiredKeys:
    def test_empty_profile_needs_no_keys(self) -> None:
        p = OnboardProfile()
        assert p.required_keys() == {}

    def test_openai_provider_needs_openai_key(self) -> None:
        p = OnboardProfile(llm_providers=[LLMProvider.OPENAI])
        keys = p.required_keys()
        assert "OPENAI_API_KEY" in keys

    def test_multiple_providers(self) -> None:
        p = OnboardProfile(
            llm_providers=[LLMProvider.OPENAI, LLMProvider.ANTHROPIC, LLMProvider.OPENROUTER]
        )
        keys = p.required_keys()
        assert "OPENAI_API_KEY" in keys
        assert "ANTHROPIC_API_KEY" in keys
        assert "OPENROUTER_API_KEY" in keys
        assert "GOOGLE_API_KEY" not in keys

    def test_e2b_environment_needs_e2b_key(self) -> None:
        # ``minif2f`` is the lowest-dependency E2B environment still in the
        # registry after the canonical-smoke cleanup removed the prior
        # ``smoke-test`` environment.
        p = OnboardProfile(environments=["minif2f"])
        keys = p.required_keys()
        assert "E2B_API_KEY" in keys

    def test_gdpeval_needs_e2b_key(self) -> None:
        p = OnboardProfile(environments=["gdpeval"])
        keys = p.required_keys()
        assert "E2B_API_KEY" in keys

    def test_researchrubrics_has_optional_exa(self) -> None:
        p = OnboardProfile(environments=["researchrubrics"])
        keys = p.required_keys()
        assert "EXA_API_KEY" in keys
        assert "E2B_API_KEY" not in keys

    def test_no_e2b_for_researchrubrics_only(self) -> None:
        p = OnboardProfile(environments=["researchrubrics"])
        keys = p.required_keys()
        assert "E2B_API_KEY" not in keys

    def test_gpu_provider_shadeform(self) -> None:
        p = OnboardProfile(training=True, gpu_provider=GPUProvider.SHADEFORM)
        keys = p.required_keys()
        assert "SHADEFORM_API_KEY" in keys

    def test_gpu_provider_lambda(self) -> None:
        p = OnboardProfile(training=True, gpu_provider=GPUProvider.LAMBDA)
        keys = p.required_keys()
        assert "LAMBDA_API_KEY" in keys

    def test_local_gpu_needs_no_provider_key(self) -> None:
        p = OnboardProfile(training=True, gpu_provider=GPUProvider.LOCAL)
        keys = p.required_keys()
        assert "SHADEFORM_API_KEY" not in keys
        assert "LAMBDA_API_KEY" not in keys
        assert "RUNPOD_API_KEY" not in keys

    def test_combined_profile(self) -> None:
        p = OnboardProfile(
            environments=["gdpeval", "researchrubrics"],
            llm_providers=[LLMProvider.OPENAI],
            training=True,
            gpu_provider=GPUProvider.RUNPOD,
        )
        keys = p.required_keys()
        assert "OPENAI_API_KEY" in keys
        assert "E2B_API_KEY" in keys
        assert "EXA_API_KEY" in keys
        assert "RUNPOD_API_KEY" in keys


class TestRequiredExtras:
    def test_empty_profile(self) -> None:
        p = OnboardProfile()
        assert p.required_extras() == []

    def test_gdpeval_needs_data_extra(self) -> None:
        p = OnboardProfile(environments=["gdpeval"])
        extras = p.required_extras()
        assert "ergon-builtins[data]" in extras

    def test_researchrubrics_needs_data_extra(self) -> None:
        p = OnboardProfile(environments=["researchrubrics"])
        extras = p.required_extras()
        assert "ergon-builtins[data]" in extras

    def test_minif2f_needs_no_data_extra(self) -> None:
        # ``minif2f`` replaces the retired ``smoke-test`` environment as
        # the smallest-dependency E2B environment.  Smoke runs use each
        # environment's real sandbox image; no separate ``smoke-test``
        # environment exists after the canonical-smoke cleanup.
        p = OnboardProfile(environments=["minif2f"])
        assert "ergon-builtins[data]" not in p.required_extras()

    def test_training_adds_infra_training(self) -> None:
        p = OnboardProfile(training=True)
        extras = p.required_extras()
        assert "ergon-infra[training]" in extras

    def test_remote_gpu_adds_skypilot(self) -> None:
        p = OnboardProfile(training=True, gpu_provider=GPUProvider.SHADEFORM)
        extras = p.required_extras()
        assert "ergon-infra[skypilot]" in extras
        assert "ergon-infra[training]" in extras

    def test_local_gpu_no_skypilot(self) -> None:
        p = OnboardProfile(training=True, gpu_provider=GPUProvider.LOCAL)
        extras = p.required_extras()
        assert "ergon-infra[skypilot]" not in extras
        assert "ergon-infra[training]" in extras

    def test_deduplicates_data_extra(self) -> None:
        p = OnboardProfile(environments=["gdpeval", "researchrubrics"])
        extras = p.required_extras()
        assert extras.count("ergon-builtins[data]") == 1

    def test_sorted_output(self) -> None:
        p = OnboardProfile(
            environments=["gdpeval"],
            training=True,
            gpu_provider=GPUProvider.SHADEFORM,
        )
        extras = p.required_extras()
        assert extras == sorted(extras)


class TestPreviouslyMissingEnvironments:
    """Regression coverage for the remaining object-bound environment choices."""

    def test_researchrubrics_vanilla_needs_data_extra(self) -> None:
        p = OnboardProfile(environments=["researchrubrics-vanilla"])
        assert "ergon-builtins[data]" in p.required_extras()


class TestOnboardingWizardSeesAllEnvironments:
    """The wizard must offer all registered environments."""

    def test_wizard_sees_all_registered_slugs(self) -> None:
        expected = {
            "minif2f",
            "swebench-verified",
            "gdpeval",
            "researchrubrics",
            "researchrubrics-vanilla",
        }
        assert expected <= set(profile_module.available_environment_slugs())
