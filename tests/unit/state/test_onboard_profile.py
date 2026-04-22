"""Unit tests for OnboardProfile: required_keys() and required_extras()."""

from ergon_cli.onboarding.profile import (
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

    def test_e2b_benchmark_needs_e2b_key(self) -> None:
        p = OnboardProfile(benchmarks=["smoke-test"])
        keys = p.required_keys()
        assert "E2B_API_KEY" in keys

    def test_gdpeval_needs_e2b_key(self) -> None:
        p = OnboardProfile(benchmarks=["gdpeval"])
        keys = p.required_keys()
        assert "E2B_API_KEY" in keys

    def test_researchrubrics_has_optional_exa(self) -> None:
        p = OnboardProfile(benchmarks=["researchrubrics"])
        keys = p.required_keys()
        assert "EXA_API_KEY" in keys
        assert "E2B_API_KEY" not in keys

    def test_no_e2b_for_researchrubrics_only(self) -> None:
        p = OnboardProfile(benchmarks=["researchrubrics"])
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
            benchmarks=["gdpeval", "researchrubrics"],
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
        p = OnboardProfile(benchmarks=["gdpeval"])
        extras = p.required_extras()
        assert "ergon-builtins[data]" in extras

    def test_researchrubrics_needs_data_extra(self) -> None:
        p = OnboardProfile(benchmarks=["researchrubrics"])
        extras = p.required_extras()
        assert "ergon-builtins[data]" in extras

    def test_smoke_test_needs_no_extra(self) -> None:
        p = OnboardProfile(benchmarks=["smoke-test"])
        assert p.required_extras() == []

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
        p = OnboardProfile(benchmarks=["gdpeval", "researchrubrics"])
        extras = p.required_extras()
        assert extras.count("ergon-builtins[data]") == 1

    def test_sorted_output(self) -> None:
        p = OnboardProfile(
            benchmarks=["gdpeval"],
            training=True,
            gpu_provider=GPUProvider.SHADEFORM,
        )
        extras = p.required_extras()
        assert extras == sorted(extras)


class TestPreviouslyMissingBenchmarks:
    """Regression: delegation-smoke and researchrubrics-smoke were absent
    from BENCHMARK_DEPS before this RFC. Verify they now appear in the
    onboarding wizard choices and produce correct deps."""

    def test_delegation_smoke_has_no_e2b(self) -> None:
        p = OnboardProfile(benchmarks=["delegation-smoke"])
        assert "E2B_API_KEY" not in p.required_keys()
        assert p.required_extras() == []

    def test_researchrubrics_smoke_has_no_e2b(self) -> None:
        p = OnboardProfile(benchmarks=["researchrubrics-smoke"])
        assert "E2B_API_KEY" not in p.required_keys()
        assert p.required_extras() == []

    def test_researchrubrics_ablated_needs_data_extra(self) -> None:
        p = OnboardProfile(benchmarks=["researchrubrics-ablated"])
        assert "ergon-builtins[data]" in p.required_extras()

    def test_researchrubrics_vanilla_needs_data_extra(self) -> None:
        p = OnboardProfile(benchmarks=["researchrubrics-vanilla"])
        assert "ergon-builtins[data]" in p.required_extras()


class TestOnboardingWizardSeesAllBenchmarks:
    """The wizard must offer all registered benchmarks."""

    def test_wizard_sees_all_registered_slugs(self) -> None:
        from ergon_builtins.registry import BENCHMARKS

        expected = {
            "smoke-test",
            "minif2f",
            "researchrubrics-smoke",
            "swebench-verified",
            "gdpeval",
            "researchrubrics",
            "researchrubrics-ablated",
            "researchrubrics-vanilla",
        }
        assert expected <= set(BENCHMARKS.keys())
