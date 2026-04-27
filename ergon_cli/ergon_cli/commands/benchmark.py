"""Benchmark subcommand: list and setup benchmarks."""

import json
import os
import sys
import time
import tomllib
from argparse import Namespace
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from e2b import Template
from ergon_core.api.json_types import JsonObject
from ergon_core.core.settings import settings

from ergon_cli.discovery import list_benchmarks
from ergon_cli.rendering import render_table


class BuildLog(Protocol):
    def __str__(self) -> str: ...


def _fail(message: str, exit_code: int = 1) -> int:
    """Print *message* to stderr and return *exit_code*."""
    print(message, file=sys.stderr)
    return exit_code


def _config_dir() -> Path:
    """Return the Ergon config directory, respecting ``ERGON_CONFIG_DIR``."""
    return Path(os.environ.get("ERGON_CONFIG_DIR", Path.home() / ".ergon"))


async def handle_benchmark(args: Namespace) -> int:
    if args.bench_action == "list":
        benchmarks = list_benchmarks()
        render_table(["Slug", "Name", "Description"], benchmarks)
        return 0
    elif args.bench_action == "setup":
        return setup_benchmark(args)
    else:
        print("Usage: ergon benchmark {list|run|setup}")
        return 1


# ---------------------------------------------------------------------------
# setup subaction
# ---------------------------------------------------------------------------


def setup_benchmark(args: Namespace) -> int:
    """Build and register the E2B sandbox template for *args.slug*.

    Uses the E2B Python SDK's ``Template.build()`` directly instead of shelling
    out to the ``e2b`` CLI.  The SDK authenticates with ``E2B_API_KEY`` only —
    no ``E2B_ACCESS_TOKEN`` needed.  (The CLI's separate access-token
    requirement is specific to its auth flow; the SDK talks to the REST API
    with the API key.)
    """

    # reason: deferred to avoid pulling heavy ergon_builtins deps at CLI startup
    from ergon_builtins.registry_core import SANDBOX_TEMPLATES

    slug: str = args.slug
    force: bool = args.force

    # 1. Validate E2B_API_KEY
    if not settings.e2b_api_key:
        return _fail(
            "Error: E2B_API_KEY is not set.\n"
            "Export your E2B API key before running this command:\n"
            "  export E2B_API_KEY=<your-key>\n"
            "Get a key at https://e2b.dev/dashboard"
        )

    # 2. Look up template dir
    if slug not in SANDBOX_TEMPLATES:
        available = ", ".join(sorted(SANDBOX_TEMPLATES)) or "(none)"
        return _fail(f"Error: unknown benchmark slug '{slug}'.\nAvailable slugs: {available}")

    template_dir = SANDBOX_TEMPLATES[slug]

    # 3. Load template spec from e2b.toml.template
    template_spec_path = template_dir / "e2b.toml.template"
    if not template_spec_path.exists():
        return _fail(f"Error: template spec not found at {template_spec_path}")

    with open(template_spec_path, "rb") as f:
        spec = tomllib.load(f)

    template_name = spec.get("template_name")
    if not template_name:
        return _fail(
            f"Error: 'template_name' not found in {template_spec_path}.\n"
            "The e2b.toml.template must declare a template_name."
        )

    # 4. Idempotency check
    config = _config_dir()
    registry_path = config / "sandbox_templates.json"

    existing_templates: dict[str, JsonObject] = {}
    if registry_path.exists():
        with open(registry_path) as f:
            existing_templates = json.load(f)

    if not force and slug in existing_templates:
        tid = existing_templates[slug].get("template_id", "unknown")
        print(f"Template already built: {tid}. Use --force to rebuild.")
        return 0

    # 5. Build via E2B SDK (authenticates with E2B_API_KEY only)
    cpu_count = int(spec.get("cpu_count", 2))
    memory_mb = int(spec.get("memory_mb", 8192))
    start_cmd = spec.get("start_cmd", "/bin/bash")
    dockerfile_name = spec.get("dockerfile", "Dockerfile")
    dockerfile_path = template_dir / dockerfile_name

    if not dockerfile_path.exists():
        return _fail(f"Error: Dockerfile not found at {dockerfile_path}")

    dockerfile_content = dockerfile_path.read_text()

    print(f"Building E2B template '{template_name}' from {template_dir} ...")
    print(f"  cpu_count={cpu_count}, memory_mb={memory_mb}")

    def _on_build_logs(log: BuildLog) -> None:
        # LogEntry repr is human-readable; raw print is fine for CLI stream.
        print(f"  [build] {log}", flush=True)

    template_def = (
        Template(file_context_path=str(template_dir))
        .from_dockerfile(dockerfile_content)
        .set_start_cmd(start_cmd=start_cmd, ready_cmd="echo ready")
    )

    t0 = time.monotonic()
    try:
        build_info = Template.build(
            template_def,
            name=template_name,
            cpu_count=cpu_count,
            memory_mb=memory_mb,
            on_build_logs=_on_build_logs,
        )
    except Exception as exc:  # slopcop: ignore[no-broad-except]
        return _fail(f"Error: E2B SDK Template.build() failed: {exc}")

    build_time = round(time.monotonic() - t0, 1)
    template_id = build_info.template_id

    # 6. Persist
    config.mkdir(parents=True, exist_ok=True)
    existing_templates[slug] = {
        "template_id": template_id,
        "template_name": template_name,
        "build_id": build_info.build_id,
        "built_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(registry_path, "w") as f:
        json.dump(existing_templates, f, indent=2)

    # 7. Report
    print(f"\nSuccess! Template ID: {template_id} (build {build_info.build_id}, {build_time}s)")
    print(
        "Now run: "
        f"`ergon experiment define {slug} --worker minif2f-react --model <model> --limit 1`"
    )
    return 0
