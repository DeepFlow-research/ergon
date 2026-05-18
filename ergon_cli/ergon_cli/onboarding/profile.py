"""OnboardProfile: user choices -> required keys and pip extras."""

from enum import Enum

from ergon_core.api.benchmark import BenchmarkRequirements
from pydantic import BaseModel, Field


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

BUILTIN_BENCHMARK_REQUIREMENTS: dict[str, BenchmarkRequirements] = {
    "gdpeval": BenchmarkRequirements(e2b=True, extras=("ergon-builtins[data]",)),
    "minif2f": BenchmarkRequirements(e2b=True),
    "researchrubrics": BenchmarkRequirements(
        extras=("ergon-builtins[data]",),
        optional_keys=("EXA_API_KEY",),
    ),
    "researchrubrics-vanilla": BenchmarkRequirements(),
    "swebench-verified": BenchmarkRequirements(e2b=True, extras=("ergon-builtins[data]",)),
}


def available_benchmark_slugs() -> list[str]:
    return sorted(BUILTIN_BENCHMARK_REQUIREMENTS)


class OnboardProfile(BaseModel):
    """Captures every user choice made during onboarding."""

    benchmarks: list[str] = Field(default_factory=list)
    llm_providers: list[LLMProvider] = Field(default_factory=list)
    training: bool = False
    gpu_provider: GPUProvider | None = None

    keys: dict[str, str] = Field(default_factory=dict)

    def required_keys(self) -> dict[str, str]:
        """Return {env_var: human_reason} derived purely from user choices."""
        benchmarks = BUILTIN_BENCHMARK_REQUIREMENTS

        result: dict[str, str] = {}

        for provider in self.llm_providers:
            env_var = PROVIDER_KEY_MAP[provider]
            result[env_var] = f"{provider.value} API access"

        if any(benchmarks[b].e2b for b in self.benchmarks if b in benchmarks):
            result["E2B_API_KEY"] = "Sandboxed code execution for selected benchmarks"

        for b in self.benchmarks:
            if b in benchmarks:
                for k in benchmarks[b].optional_keys:
                    result.setdefault(k, f"Optional for {b}")

        if self.gpu_provider and self.gpu_provider != GPUProvider.LOCAL:
            env_var = GPU_PROVIDER_KEY_MAP[self.gpu_provider]
            result[env_var] = f"GPU provisioning via {self.gpu_provider.value}"

        return result

    def required_extras(self) -> list[str]:
        """Pip extras to install based on choices."""
        benchmarks = BUILTIN_BENCHMARK_REQUIREMENTS

        extras: set[str] = set()
        for b in self.benchmarks:
            if b in benchmarks:
                for e in benchmarks[b].extras:
                    extras.add(e)
        if self.training:
            extras.add("ergon-infra[training]")
        if self.gpu_provider and self.gpu_provider != GPUProvider.LOCAL:
            extras.add("ergon-infra[skypilot]")
        return sorted(extras)
