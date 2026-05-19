"""Benchmark sandbox template lookup helpers."""

from pathlib import Path

from ergon_cli.domains.benchmarks.templates import sandbox_template_for, setup_benchmark_slugs

SANDBOX_TEMPLATES: dict[str, Path] = {
    slug: sandbox_template_for(slug) for slug in setup_benchmark_slugs()
}
