"""OnboardProfile: user choices -> required keys and pip extras."""

from enum import Enum

from pydantic import BaseModel, Field

from ergon_core.api.benchmark_deps import BenchmarkDeps  # noqa: F401 — re-exported for CLI callers


class LLMProvider(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    OPENROUTER = "openrouter"


class GPUProvider(str, Enum):
    LOCAL = "local"
    SHADEFORM = "shadeform"
    LAMBDA = "lambda"
    RUNPOD = "runpod"


PROVIDER_KEY_MAP: dict[LLMProvider, str] = {
    LLMProvider.OPENAI: "OPENAI_API_KEY",
    LLMProvider.ANTHROPIC: "ANTHROPIC_API_KEY",
    LLMProvider.GOOGLE: "GOOGLE_API_KEY",
    LLMProvider.OPENROUTER: "OPENROUTER_API_KEY",
}

GPU_PROVIDER_KEY_MAP: dict[GPUProvider, str] = {
    GPUProvider.SHADEFORM: "SHADEFORM_API_KEY",
    GPUProvider.LAMBDA: "LAMBDA_API_KEY",
    GPUProvider.RUNPOD: "RUNPOD_API_KEY",
}


class OnboardProfile(BaseModel):
    """Captures every user choice made during onboarding."""

    benchmarks: list[str] = Field(default_factory=list)
    llm_providers: list[LLMProvider] = Field(default_factory=list)
    training: bool = False
    gpu_provider: GPUProvider | None = None

    keys: dict[str, str] = Field(default_factory=dict)

    def required_keys(self) -> dict[str, str]:
        """Return {env_var: human_reason} derived purely from user choices."""
        # reason: deferred import avoids circular dep at CLI startup; registry
        # depends on ergon_builtins which depends on ergon_core.
        from ergon_builtins.registry import BENCHMARKS

        result: dict[str, str] = {}

        for provider in self.llm_providers:
            env_var = PROVIDER_KEY_MAP[provider]
            result[env_var] = f"{provider.value} API access"

        if any(BENCHMARKS[b].onboarding_deps.e2b for b in self.benchmarks if b in BENCHMARKS):
            result["E2B_API_KEY"] = "Sandboxed code execution for selected benchmarks"

        for b in self.benchmarks:
            if b in BENCHMARKS:
                for k in BENCHMARKS[b].onboarding_deps.optional_keys:
                    result.setdefault(k, f"Optional for {b}")

        if self.gpu_provider and self.gpu_provider != GPUProvider.LOCAL:
            env_var = GPU_PROVIDER_KEY_MAP[self.gpu_provider]
            result[env_var] = f"GPU provisioning via {self.gpu_provider.value}"

        return result

    def required_extras(self) -> list[str]:
        """Pip extras to install based on choices."""
        # reason: deferred import avoids circular dep at CLI startup; registry
        # depends on ergon_builtins which depends on ergon_core.
        from ergon_builtins.registry import BENCHMARKS

        extras: set[str] = set()
        for b in self.benchmarks:
            if b in BENCHMARKS:
                for e in BENCHMARKS[b].onboarding_deps.extras:
                    extras.add(e)
        if self.training:
            extras.add("ergon-infra[training]")
        if self.gpu_provider and self.gpu_provider != GPUProvider.LOCAL:
            extras.add("ergon-infra[skypilot]")
        return sorted(extras)
