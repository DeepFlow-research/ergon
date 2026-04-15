"""Benchmark subcommand: list, run, and setup benchmarks."""

import asyncio
import json
import os
import shutil
import subprocess
import sys
import time
import tomllib
from argparse import Namespace
from datetime import datetime, timezone
from pathlib import Path

import inngest

from ergon_cli.composition import build_experiment
from ergon_cli.discovery import list_benchmarks
from ergon_cli.rendering import render_run_result, render_table
from ergon_core.api.handles import ExperimentRunHandle
from ergon_core.core.persistence.shared.db import ensure_db, get_session
from ergon_core.core.persistence.shared.enums import TERMINAL_RUN_STATUSES
from ergon_core.core.persistence.telemetry.models import RunRecord
from ergon_core.core.runtime.events.task_events import WorkflowStartedEvent
from ergon_core.core.runtime.inngest_client import inngest_client
from ergon_core.core.runtime.services.cohort_service import experiment_cohort_service
from ergon_core.core.runtime.services.run_service import create_run


def _fail(message: str, exit_code: int = 1) -> int:
    """Print *message* to stderr and return *exit_code*."""
    print(message, file=sys.stderr)
    return exit_code


def _config_dir() -> Path:
    """Return the Ergon config directory, respecting ``ERGON_CONFIG_DIR``."""
    return Path(os.environ.get("ERGON_CONFIG_DIR", Path.home() / ".ergon"))


def handle_benchmark(args: Namespace) -> int:
    if args.bench_action == "list":
        benchmarks = list_benchmarks()
        render_table(["Slug", "Name", "Description"], benchmarks)
        return 0
    elif args.bench_action == "run":
        return run_benchmark(args)
    elif args.bench_action == "setup":
        return setup_benchmark(args)
    else:
        print("Usage: ergon benchmark {list|run|setup}")
        return 1


# ---------------------------------------------------------------------------
# setup subaction
# ---------------------------------------------------------------------------


def setup_benchmark(args: Namespace) -> int:  # noqa: C901 — linear flow, not complex
    """Build and register the E2B sandbox template for *args.slug*."""

    # reason: deferred to avoid pulling heavy ergon_builtins deps at CLI startup
    from ergon_builtins.registry_core import SANDBOX_TEMPLATES

    slug: str = args.slug
    force: bool = args.force

    # 1. Validate E2B CLI is installed
    if shutil.which("e2b") is None:
        return _fail(
            "Error: the 'e2b' CLI is not installed.\n"
            "Install it from https://e2b.dev/docs/cli and try again."
        )

    # 2. Validate E2B_API_KEY
    if not os.environ.get("E2B_API_KEY"):
        return _fail(
            "Error: E2B_API_KEY is not set.\n"
            "Export your E2B API key before running this command:\n"
            "  export E2B_API_KEY=<your-key>\n"
            "Get a key at https://e2b.dev/dashboard"
        )

    # 3. Look up template dir
    if slug not in SANDBOX_TEMPLATES:
        available = ", ".join(sorted(SANDBOX_TEMPLATES)) or "(none)"
        return _fail(
            f"Error: unknown benchmark slug '{slug}'.\n"
            f"Available slugs: {available}"
        )

    template_dir = SANDBOX_TEMPLATES[slug]

    # 4. Load template spec from e2b.toml.template
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

    # 5. Idempotency check
    config = _config_dir()
    registry_path = config / "sandbox_templates.json"

    existing_templates: dict[str, object] = {}
    if registry_path.exists():
        with open(registry_path) as f:
            existing_templates = json.load(f)

    if not force and slug in existing_templates:
        tid = existing_templates[slug].get("template_id", "unknown")  # type: ignore[union-attr]
        print(f"Template already built: {tid}. Use --force to rebuild.")
        return 0

    # 6. Invoke e2b template build
    cpu_count = str(spec.get("cpu_count", 2))
    memory_mb = str(spec.get("memory_mb", 8192))
    start_cmd = spec.get("start_cmd", "/bin/bash")
    dockerfile = spec.get("dockerfile", "Dockerfile")

    cmd = [
        "e2b",
        "template",
        "build",
        "--dockerfile",
        dockerfile,
        "--name",
        template_name,
        "--cmd",
        start_cmd,
        "--cpu-count",
        cpu_count,
        "--memory-mb",
        memory_mb,
    ]

    print(f"Building E2B template '{template_name}' from {template_dir} ...")
    result = subprocess.run(cmd, cwd=template_dir)

    if result.returncode != 0:
        return _fail(f"Error: 'e2b template build' failed with exit code {result.returncode}.")

    # 7. Parse template_id from generated e2b.toml
    generated_toml = template_dir / "e2b.toml"
    if not generated_toml.exists():
        return _fail(
            "Error: e2b.toml was not created by the build command.\n"
            "The E2B CLI may have changed its output format."
        )

    with open(generated_toml, "rb") as f:
        built = tomllib.load(f)

    template_id = built.get("template_id")
    if not template_id:
        return _fail(
            "Error: 'template_id' not found in generated e2b.toml.\n"
            "The E2B CLI may have changed its output format."
        )

    # 8. Persist
    config.mkdir(parents=True, exist_ok=True)
    existing_templates[slug] = {
        "template_id": template_id,
        "template_name": template_name,
        "built_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(registry_path, "w") as f:
        json.dump(existing_templates, f, indent=2)

    # 9. Report
    print(f"\nSuccess! Template ID: {template_id}")
    print(
        f"Now run: `ergon benchmark run {slug}"
        " --worker minif2f-react --model <model> --limit 1`"
    )
    return 0


def run_benchmark(args: Namespace) -> int:
    ensure_db()

    experiment = build_experiment(
        benchmark_slug=args.slug,
        model=args.model,
        worker_slug=args.worker,
        evaluator_slug=args.evaluator,
        workflow=args.workflow,
        limit=args.limit,
    )
    experiment.validate()
    persisted = experiment.persist()
    render_run_result(persisted)
    print(f"\nExperiment persisted: {persisted.definition_id}")

    cohort_name = args.cohort or f"{args.slug}"
    cohort = experiment_cohort_service.resolve_or_create(
        name=cohort_name,
        description=f"Benchmark: {args.slug} | worker: {args.worker} | evaluator: {args.evaluator}",
        created_by="ergon-cli",
    )
    print(f"\nCohort: {cohort.name} (id={cohort.id})")

    print("\nCreating run and dispatching via Inngest...")
    run_handle = asyncio.run(
        _create_and_dispatch(persisted, timeout=args.timeout, cohort_id=cohort.id)
    )

    print("\nRun completed:")
    print(f"  Run ID:     {run_handle.run_id}")
    print(f"  Status:     {run_handle.status}")
    print(f"  Benchmark:  {run_handle.benchmark_type}")
    return 0 if run_handle.status == "completed" else 1


async def _create_and_dispatch(persisted, timeout: int = 600, cohort_id=None):
    run = create_run(persisted, cohort_id=cohort_id)
    print(f"  Run ID: {run.id}")

    event = WorkflowStartedEvent(
        run_id=run.id,
        definition_id=persisted.definition_id,
    )
    await inngest_client.send(
        inngest.Event(
            name=WorkflowStartedEvent.name,
            data=event.model_dump(mode="json"),
        )
    )
    print("  WorkflowStartedEvent emitted. Polling for completion...")

    start = time.time()
    terminal = TERMINAL_RUN_STATUSES
    poll_interval = 2.0

    while True:
        elapsed = time.time() - start
        if elapsed > timeout:
            print(f"  TIMEOUT after {timeout}s")
            return ExperimentRunHandle(
                run_id=run.id,
                definition_id=persisted.definition_id,
                benchmark_type=persisted.benchmark_type,
                status="timeout",
            )

        session = get_session()
        try:
            current = session.get(RunRecord, run.id)
            if current and current.status in terminal:
                return ExperimentRunHandle(
                    run_id=run.id,
                    definition_id=persisted.definition_id,
                    benchmark_type=persisted.benchmark_type,
                    status=current.status,
                )
            status = current.status if current else "unknown"
        finally:
            session.close()

        mins = int(elapsed) // 60
        secs = int(elapsed) % 60
        print(f"  [{mins:02d}:{secs:02d}] status={status}")
        await asyncio.sleep(poll_interval)
