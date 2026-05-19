"""Benchmark sandbox template lookup helpers."""

from pathlib import Path

_REPO_ROOT = Path(__file__).parents[3]

SANDBOX_TEMPLATES: dict[str, Path] = {
    "minif2f": _REPO_ROOT / "ergon_builtins/ergon_builtins/benchmarks/minif2f/sandbox_template",
    "swebench-verified": _REPO_ROOT
    / "ergon_builtins/ergon_builtins/benchmarks/swebench_verified/sandbox_template",
}


def sandbox_template_for(slug: str) -> Path:
    return SANDBOX_TEMPLATES[slug]
