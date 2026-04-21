"""Benchmark subcommand: list, run, and setup benchmarks."""

import asyncio
import json
import os
import sys
import time
import tomllib
from argparse import Namespace
from datetime import datetime, timezone
from pathlib import Path

import inngest
from e2b import Template

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
from ergon_core.core.settings import settings


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
    """Build and register the E2B sandbox template for *args.slug*.

    Dispatches off ``Benchmark.template_spec`` instead of the hardcoded
    ``SANDBOX_TEMPLATES`` dict. No explicit dispatch table is needed; the spec
    carries all information.
    """
    # reason: deferred to avoid pulling heavy ergon_builtins deps at CLI startup
    from ergon_builtins.registry_core import BENCHMARKS

    # reason: deferred alongside BENCHMARKS import above to keep startup cost low
    from ergon_core.api.template_spec import NoSetup, TemplateSpec, _NoSetupType

    slug: str = args.slug
    force: bool = args.force

    # 1. Look up benchmark class
    if slug not in BENCHMARKS:
        available = ", ".join(sorted(BENCHMARKS)) or "(none)"
        return _fail(f"Error: unknown benchmark slug '{slug}'.\nAvailable slugs: {available}")

    benchmark_cls = BENCHMARKS[slug]

    # 2. Read template_spec
    spec = benchmark_cls.template_spec

    # 3. NoSetup sentinel — nothing to do
    if isinstance(spec, _NoSetupType):
        print(f"Benchmark '{slug}' declares NoSetup: no template build required.")
        return 0

    if not isinstance(spec, TemplateSpec):
        return _fail(
            f"Error: '{slug}'.template_spec is neither TemplateSpec nor NoSetup. Got: {spec!r}"
        )

    # 4. runtime_install only — deferred to sandbox prep; no build step needed
    if spec.runtime_install and spec.build_recipe_path is None and spec.e2b_template_id is None:
        pkgs = ", ".join(spec.runtime_install)
        print(
            f"Benchmark '{slug}' installs packages at sandbox-prep time ({pkgs}). "
            "No template build required."
        )
        return 0

    # 5. E2B template required
    if not settings.e2b_api_key:
        return _fail(
            "Error: E2B_API_KEY is not set.\n"
            "Export your E2B API key before running this command:\n"
            "  export E2B_API_KEY=<your-key>\n"
            "Get a key at https://e2b.dev/dashboard"
        )

    # 6. No build recipe — verify-only path
    if spec.build_recipe_path is None:
        print(
            f"Benchmark '{slug}' references E2B template '{spec.e2b_template_id}' "
            "but declares no build_recipe_path. Cannot rebuild automatically.\n"
            f"Ensure template '{spec.e2b_template_id}' exists in your E2B account."
        )
        return 0

    template_dir = spec.build_recipe_path

    # 7. Load e2b.toml.template from the recipe directory
    template_spec_path = template_dir / "e2b.toml.template"
    if not template_spec_path.exists():
        return _fail(f"Error: template spec not found at {template_spec_path}")

    with open(template_spec_path, "rb") as f:
        toml_spec = tomllib.load(f)

    template_name = toml_spec.get("template_name") or spec.e2b_template_id
    if not template_name:
        return _fail(
            f"Error: no template_name in {template_spec_path} and "
            "no e2b_template_id on TemplateSpec."
        )

    # 8. Idempotency check
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

    # 9. Build via E2B SDK
    cpu_count = int(toml_spec.get("cpu_count", 2))
    memory_mb = int(toml_spec.get("memory_mb", 8192))
    start_cmd = toml_spec.get("start_cmd", "/bin/bash")
    dockerfile_name = toml_spec.get("dockerfile", "Dockerfile")
    dockerfile_path = template_dir / dockerfile_name

    if not dockerfile_path.exists():
        return _fail(f"Error: Dockerfile not found at {dockerfile_path}")

    dockerfile_content = dockerfile_path.read_text()

    print(f"Building E2B template '{template_name}' from {template_dir} ...")
    print(f"  cpu_count={cpu_count}, memory_mb={memory_mb}")

    def _on_build_logs(log: object) -> None:
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
    except Exception as exc:  # noqa: BLE001  # slopcop: ignore[no-broad-except]
        return _fail(f"Error: E2B SDK Template.build() failed: {exc}")

    build_time = round(time.monotonic() - t0, 1)
    template_id = build_info.template_id

    # 10. Persist
    config.mkdir(parents=True, exist_ok=True)
    existing_templates[slug] = {
        "template_id": template_id,
        "template_name": template_name,
        "build_id": build_info.build_id,
        "built_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(registry_path, "w") as f:
        json.dump(existing_templates, f, indent=2)

    # 11. Report
    print(f"\nSuccess! Template ID: {template_id} (build {build_info.build_id}, {build_time}s)")
    print(f"Now run: `ergon benchmark run {slug} --worker <worker> --model <model> --limit 1`")
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
