"""OnboardProfile: user choices -> required keys and pip extras."""

from enum import Enum
from typing import Literal

from ergon_builtins.benchmarks.catalog import benchmark_cli_metadata
from pydantic import BaseModel, Field

EnvKeyOwner = Literal[
    "core-runtime",
    "model-provider-runtime",
    "benchmark-evaluation-runtime",
    "infra-training-runtime",
    "local-networking-dev",
]


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

ENV_KEY_OWNERS: dict[str, EnvKeyOwner] = {
    "DATABASE_URL": "core-runtime",
    "ERGON_DATABASE_URL": "core-runtime",
    "INNGEST_EVENT_KEY": "core-runtime",
    "INNGEST_DEV": "core-runtime",
    "INNGEST_API_BASE_URL": "core-runtime",
    "OPENAI_API_KEY": "model-provider-runtime",
    "ANTHROPIC_API_KEY": "model-provider-runtime",
    "GOOGLE_API_KEY": "model-provider-runtime",
    "OPENROUTER_API_KEY": "model-provider-runtime",
    "E2B_API_KEY": "benchmark-evaluation-runtime",
    "EXA_API_KEY": "benchmark-evaluation-runtime",
    "SHADEFORM_API_KEY": "infra-training-runtime",
    "LAMBDA_API_KEY": "infra-training-runtime",
    "RUNPOD_API_KEY": "infra-training-runtime",
    "TAILSCALE_AUTH_KEY": "local-networking-dev",
    "TAILSCALE_MACBOOK_IP": "local-networking-dev",
}


def available_benchmark_slugs() -> list[str]:
    return sorted(benchmark_cli_metadata())


class OnboardProfile(BaseModel):
    """Captures every user choice made during onboarding."""

    benchmarks: list[str] = Field(default_factory=list)
    llm_providers: list[LLMProvider] = Field(default_factory=list)
    training: bool = False
    gpu_provider: GPUProvider | None = None

    keys: dict[str, str] = Field(default_factory=dict)

    def required_keys(self) -> dict[str, str]:
        """Return {env_var: human_reason} derived purely from user choices."""
        benchmarks = benchmark_cli_metadata()

        result: dict[str, str] = {}

        for provider in self.llm_providers:
            env_var = PROVIDER_KEY_MAP[provider]
            result[env_var] = f"{provider.value} API access"

        if any("E2B_API_KEY" in benchmarks[b].env_keys for b in self.benchmarks if b in benchmarks):
            result["E2B_API_KEY"] = "Sandboxed code execution for selected benchmarks"

        for b in self.benchmarks:
            if b in benchmarks:
                for key in benchmarks[b].env_keys:
                    if key == "E2B_API_KEY":
                        continue
                    result.setdefault(key, f"Optional for {b}")

        if self.gpu_provider and self.gpu_provider != GPUProvider.LOCAL:
            env_var = GPU_PROVIDER_KEY_MAP[self.gpu_provider]
            result[env_var] = f"GPU provisioning via {self.gpu_provider.value}"

        return result

    def required_extras(self) -> list[str]:
        """Pip extras to install based on choices."""
        benchmarks = benchmark_cli_metadata()

        extras: set[str] = set()
        for benchmark in self.benchmarks:
            if benchmark in benchmarks:
                extras.update(benchmarks[benchmark].required_packages)
        if self.training:
            extras.add("ergon-infra[training]")
        if self.gpu_provider and self.gpu_provider != GPUProvider.LOCAL:
            extras.add("ergon-infra[skypilot]")
        return sorted(extras)
