import json
import os
import sys
import time
import tomllib
from datetime import datetime, timezone
from pathlib import Path

from e2b import Template
from ergon_builtins.benchmarks.catalog import benchmark_cli_metadata
from ergon_cli.domains.benchmarks.models import BenchmarkCommand
from ergon_cli.domains.benchmarks.templates import sandbox_template_for, setup_benchmark_slugs
from ergon_core.core.shared.json_types import JsonObject
from ergon_core.core.shared.settings import settings
from pydantic import BaseModel, ConfigDict


def list_benchmark_rows() -> list[list[str]]:
    return [
        [metadata.slug, metadata.name, metadata.description]
        for metadata in sorted(benchmark_cli_metadata().values(), key=lambda item: item.slug)
    ]


def setup_benchmark(command: BenchmarkCommand) -> int:
    if command.slug is None:
        return _fail("Usage: ergon benchmark setup <slug>")

    slug = command.slug
    force = command.force

    if not settings.e2b_api_key:
        return _fail(
            "Error: E2B_API_KEY is not set.\n"
            "Export your E2B API key before running this command:\n"
            "  export E2B_API_KEY=<your-key>\n"
            "Get a key at https://e2b.dev/dashboard"
        )

    template_dir = _template_dir_for(slug)
    if template_dir is None:
        available = ", ".join(setup_benchmark_slugs()) or "(none)"
        return _fail(f"Error: unknown benchmark slug '{slug}'.\nAvailable slugs: {available}")

    template_spec = _load_template_spec(template_dir)
    if isinstance(template_spec, str):
        return _fail(template_spec)

    config = _config_dir()
    registry_path = config / "sandbox_templates.json"
    existing_templates = _read_registry(registry_path)

    if not force and slug in existing_templates:
        tid = existing_templates[slug].get("template_id", "unknown")
        print(f"Template already built: {tid}. Use --force to rebuild.")
        return 0

    dockerfile_path = template_dir / template_spec.dockerfile_name

    if not dockerfile_path.exists():
        return _fail(f"Error: Dockerfile not found at {dockerfile_path}")

    dockerfile_content = dockerfile_path.read_text()

    print(f"Building E2B template '{template_spec.template_name}' from {template_dir} ...")
    print(f"  cpu_count={template_spec.cpu_count}, memory_mb={template_spec.memory_mb}")

    def _on_build_logs(log: object) -> None:
        print(f"  [build] {log}", flush=True)

    template_def = (
        Template(file_context_path=str(template_dir))
        .from_dockerfile(dockerfile_content)
        .set_start_cmd(start_cmd=template_spec.start_cmd, ready_cmd="echo ready")
    )

    t0 = time.monotonic()
    try:
        build_info = Template.build(
            template_def,
            name=template_spec.template_name,
            cpu_count=template_spec.cpu_count,
            memory_mb=template_spec.memory_mb,
            on_build_logs=_on_build_logs,
        )
    except Exception as exc:  # slopcop: ignore[no-broad-except]
        return _fail(f"Error: E2B SDK Template.build() failed: {exc}")

    build_time = round(time.monotonic() - t0, 1)
    template_id = build_info.template_id

    config.mkdir(parents=True, exist_ok=True)
    existing_templates[slug] = {
        "template_id": template_id,
        "template_name": template_spec.template_name,
        "build_id": build_info.build_id,
        "built_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(registry_path, "w") as f:
        json.dump(existing_templates, f, indent=2)

    print(f"\nSuccess! Template ID: {template_id} (build {build_info.build_id}, {build_time}s)")
    return 0


def _config_dir() -> Path:
    return Path(os.environ.get("ERGON_CONFIG_DIR", Path.home() / ".ergon"))


def _fail(message: str, exit_code: int = 1) -> int:
    print(message, file=sys.stderr)
    return exit_code


class _TemplateSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    template_name: str
    cpu_count: int = 2
    memory_mb: int = 8192
    start_cmd: str = "/bin/bash"
    dockerfile_name: str = "Dockerfile"


def _template_dir_for(slug: str) -> Path | None:
    try:
        return sandbox_template_for(slug)
    except KeyError:
        return None


def _load_template_spec(template_dir: Path) -> _TemplateSpec | str:
    template_spec_path = template_dir / "e2b.toml.template"
    if not template_spec_path.exists():
        return f"Error: template spec not found at {template_spec_path}"

    with open(template_spec_path, "rb") as f:
        spec = tomllib.load(f)

    template_name = spec.get("template_name")
    if not template_name:
        return (
            f"Error: 'template_name' not found in {template_spec_path}.\n"
            "The e2b.toml.template must declare a template_name."
        )
    return _TemplateSpec(
        template_name=template_name,
        cpu_count=int(spec.get("cpu_count", 2)),
        memory_mb=int(spec.get("memory_mb", 8192)),
        start_cmd=spec.get("start_cmd", "/bin/bash"),
        dockerfile_name=spec.get("dockerfile", "Dockerfile"),
    )


def _read_registry(registry_path: Path) -> dict[str, JsonObject]:
    if not registry_path.exists():
        return {}
    with open(registry_path) as f:
        return json.load(f)
