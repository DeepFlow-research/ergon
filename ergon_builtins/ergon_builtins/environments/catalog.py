"""Builtins-owned environment metadata for CLI setup/onboarding."""

from collections.abc import Mapping
from pathlib import Path

from pydantic import BaseModel, ConfigDict


class EnvironmentCliMetadata(BaseModel):
    model_config = ConfigDict(frozen=True)

    slug: str
    name: str
    description: str
    sandbox_template: Path | None = None
    required_packages: tuple[str, ...] = ()
    env_keys: tuple[str, ...] = ()
    supports_setup: bool = False


_ENVIRONMENT_TEMPLATE_ROOT = Path(__file__).parents[1] / "benchmarks"

_METADATA: dict[str, EnvironmentCliMetadata] = {
    "gdpeval": EnvironmentCliMetadata(
        slug="gdpeval",
        name="gdpeval",
        description="Environment for GDP document-processing evaluation tasks.",
        required_packages=("ergon-builtins[data]",),
        env_keys=("E2B_API_KEY",),
    ),
    "minif2f": EnvironmentCliMetadata(
        slug="minif2f",
        name="minif2f",
        description="Environment backed by MiniF2F theorem-proving tasks.",
        sandbox_template=_ENVIRONMENT_TEMPLATE_ROOT / "minif2f" / "sandbox_template",
        env_keys=("E2B_API_KEY",),
        supports_setup=True,
    ),
    "researchrubrics": EnvironmentCliMetadata(
        slug="researchrubrics",
        name="researchrubrics",
        description="Environment backed by ScaleAI ResearchRubrics samples.",
        required_packages=("ergon-builtins[data]",),
        env_keys=("EXA_API_KEY",),
    ),
    "researchrubrics-vanilla": EnvironmentCliMetadata(
        slug="researchrubrics-vanilla",
        name="researchrubrics-vanilla",
        description="Vanilla ResearchRubrics baseline environment.",
        required_packages=("ergon-builtins[data]",),
    ),
    "swebench-verified": EnvironmentCliMetadata(
        slug="swebench-verified",
        name="swebench-verified",
        description="Environment backed by SWE-Bench Verified.",
        sandbox_template=_ENVIRONMENT_TEMPLATE_ROOT / "swebench_verified" / "sandbox_template",
        required_packages=("ergon-builtins[data]",),
        env_keys=("E2B_API_KEY",),
        supports_setup=True,
    ),
}


def environment_cli_metadata() -> Mapping[str, EnvironmentCliMetadata]:
    return dict(_METADATA)
