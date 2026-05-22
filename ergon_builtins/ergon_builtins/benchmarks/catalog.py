"""Builtins-owned benchmark metadata for CLI setup/onboarding."""

from collections.abc import Mapping
from pathlib import Path

from pydantic import BaseModel, ConfigDict


class BenchmarkCliMetadata(BaseModel):
    model_config = ConfigDict(frozen=True)

    slug: str
    name: str
    description: str
    sandbox_template: Path | None = None
    required_packages: tuple[str, ...] = ()
    env_keys: tuple[str, ...] = ()
    supports_setup: bool = False


_BENCHMARK_ROOT = Path(__file__).parent

_METADATA: dict[str, BenchmarkCliMetadata] = {
    "gdpeval": BenchmarkCliMetadata(
        slug="gdpeval",
        name="gdpeval",
        description="Benchmark for GDP document-processing evaluation tasks.",
        required_packages=("ergon-builtins[data]",),
        env_keys=("E2B_API_KEY",),
    ),
    "minif2f": BenchmarkCliMetadata(
        slug="minif2f",
        name="minif2f",
        description="Benchmark backed by MiniF2F theorem-proving tasks.",
        sandbox_template=_BENCHMARK_ROOT / "minif2f" / "sandbox_template",
        env_keys=("E2B_API_KEY",),
        supports_setup=True,
    ),
    "researchrubrics": BenchmarkCliMetadata(
        slug="researchrubrics",
        name="researchrubrics",
        description="Benchmark backed by ScaleAI ResearchRubrics samples.",
        required_packages=("ergon-builtins[data]",),
        env_keys=("EXA_API_KEY",),
    ),
    "researchrubrics-vanilla": BenchmarkCliMetadata(
        slug="researchrubrics-vanilla",
        name="researchrubrics-vanilla",
        description="Vanilla ResearchRubrics baseline benchmark.",
        required_packages=("ergon-builtins[data]",),
    ),
    "swebench-verified": BenchmarkCliMetadata(
        slug="swebench-verified",
        name="swebench-verified",
        description="Benchmark backed by SWE-Bench Verified.",
        sandbox_template=_BENCHMARK_ROOT / "swebench_verified" / "sandbox_template",
        required_packages=("ergon-builtins[data]",),
        env_keys=("E2B_API_KEY",),
        supports_setup=True,
    ),
}


def benchmark_cli_metadata() -> Mapping[str, BenchmarkCliMetadata]:
    return dict(_METADATA)
