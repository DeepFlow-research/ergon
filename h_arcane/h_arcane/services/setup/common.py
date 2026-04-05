"""Shared helpers for benchmark setup services."""

from __future__ import annotations

from pathlib import Path

DEFAULT_RESEARCHRUBRICS_DATASET = "cm2435cm2435cm2435/researchrubrics-ablated"
# TODO: Re-add `gdpeval` here once its benchmark assets are hosted cleanly on Hugging Face.
SUPPORTED_BENCHMARKS = ("minif2f", "researchrubrics")
# Benchmarks that currently expose workflow factories and can be launched via
# the workflow-construction branch of `magym benchmark run`.
WORKFLOW_RUN_BENCHMARKS = ("smoke_test",)

# Benchmarks that should be launched from previously seeded Experiment rows.
SEEDED_EXPERIMENT_RUN_BENCHMARKS = ("minif2f", "researchrubrics")

# All benchmarks currently supported by the top-level run command.
RUNNABLE_BENCHMARKS = WORKFLOW_RUN_BENCHMARKS + SEEDED_EXPERIMENT_RUN_BENCHMARKS
MINIF2F_REQUIRED_FILES = ("lean/src/valid.lean", "lean/src/test.lean")


def project_root() -> Path:
    """Return the repository root for the Arcane project."""
    return Path(__file__).resolve().parents[3]


def env_file_path() -> Path:
    """Return the local .env path."""
    return project_root() / ".env"


def parse_env_file(path: Path | None = None) -> dict[str, str]:
    """Parse a simple KEY=VALUE env file."""
    env_path = path or env_file_path()
    if not env_path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values
