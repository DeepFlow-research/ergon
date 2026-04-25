"""Rollout artifact dump for the real-LLM tier.

A rollout harness (not a TDD tier): its job is to trigger a real-LLM
benchmark run and then dump an exhaustive snapshot of what happened into
a per-run directory so a future agent session (or a human) can read the
artifacts and reason about whether the agent succeeded, and what to
tweak in either the model or the simulator to iterate.

The test asserts only that the benchmark reached a terminal status.
Everything else is captured as artifacts.

Artifact layout:

    tests/real_llm/.rollouts/<timestamp>-<run_id>/
    ├── manifest.json            # run metadata + key fingerprints
    ├── db/                      # one jsonl/json per persistence table
    │   ├── run_record.json
    │   ├── run_task_executions.jsonl
    │   ├── run_resources.jsonl
    │   ├── run_task_evaluations.jsonl
    │   ├── run_generation_turns.jsonl
    │   ├── sandbox_events.jsonl
    │   ├── run_graph_nodes.jsonl
    │   ├── run_graph_edges.jsonl
    │   ├── run_graph_mutations.jsonl
    │   └── run_context_events.jsonl
    ├── screenshots/
    │   ├── cohort_index.png
    │   └── run_detail.png
    └── report.md                # stitched human/agent-readable summary
"""

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any  # slopcop: ignore[no-typing-any]
from uuid import UUID

from sqlmodel import select

from ergon_core.core.persistence.context.models import RunContextEvent
from ergon_core.core.persistence.graph.models import (
    RunGraphEdge,
    RunGraphMutation,
    RunGraphNode,
)
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.telemetry.models import (
    RunGenerationTurn,
    RunRecord,
    RunResource,
    RunTaskEvaluation,
    RunTaskExecution,
    SandboxEvent,
)

logger = logging.getLogger(__name__)

# Host-side location where every rollout is written.
_ROLLOUTS_ROOT = Path(__file__).parent / ".rollouts"


def rollout_dir(run_id: UUID) -> Path:
    """Return (and ensure) ``tests/real_llm/.rollouts/<ts>-<run_id>/``."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = _ROLLOUTS_ROOT / f"{ts}-{run_id}"
    (out / "db").mkdir(parents=True, exist_ok=True)
    (out / "screenshots").mkdir(parents=True, exist_ok=True)
    return out


def _write_jsonl(path: Path, rows: list[Any]) -> int:  # slopcop: ignore[no-typing-any]
    """Write each row as a single JSON line.  Returns row count."""
    with path.open("w") as f:
        for row in rows:
            f.write(row.model_dump_json())
            f.write("\n")
    return len(rows)


def _write_json_model(path: Path, row: Any) -> None:  # slopcop: ignore[no-typing-any]
    """Write a SQLModel row as pretty JSON via its ``model_dump_json``."""
    path.write_text(row.model_dump_json(indent=2))


def dump_rollout(run_id: UUID, out_dir: Path) -> dict[str, int]:
    """Dump every persistence table for a run into ``out_dir/db/``.

    Returns a ``{table_name: row_count}`` map for the manifest.

    Each table's rows are filtered by ``run_id`` (all relevant tables
    carry it as either an FK or an indexed column).  Rows are serialised
    via SQLModel's ``.model_dump_json()`` so the dump preserves the
    exact Pydantic schema — downstream readers can ``RunRecord.model_validate_json``
    to round-trip.
    """
    db_dir = out_dir / "db"
    counts: dict[str, int] = {}

    with get_session() as session:
        run = session.exec(select(RunRecord).where(RunRecord.id == run_id)).first()
        if run is None:
            raise RuntimeError(f"run {run_id} not found in DB — cannot dump rollout")
        _write_json_model(db_dir / "run_record.json", run)
        counts["run_record"] = 1

        counts["run_task_executions"] = _write_jsonl(
            db_dir / "run_task_executions.jsonl",
            list(
                session.exec(
                    select(RunTaskExecution).where(RunTaskExecution.run_id == run_id)
                ).all()
            ),
        )
        counts["run_resources"] = _write_jsonl(
            db_dir / "run_resources.jsonl",
            list(session.exec(select(RunResource).where(RunResource.run_id == run_id)).all()),
        )
        counts["run_task_evaluations"] = _write_jsonl(
            db_dir / "run_task_evaluations.jsonl",
            list(
                session.exec(
                    select(RunTaskEvaluation).where(RunTaskEvaluation.run_id == run_id)
                ).all()
            ),
        )
        counts["run_generation_turns"] = _write_jsonl(
            db_dir / "run_generation_turns.jsonl",
            list(
                session.exec(
                    select(RunGenerationTurn).where(RunGenerationTurn.run_id == run_id)
                ).all()
            ),
        )
        counts["sandbox_events"] = _write_jsonl(
            db_dir / "sandbox_events.jsonl",
            list(session.exec(select(SandboxEvent).where(SandboxEvent.run_id == run_id)).all()),
        )
        counts["run_graph_nodes"] = _write_jsonl(
            db_dir / "run_graph_nodes.jsonl",
            list(session.exec(select(RunGraphNode).where(RunGraphNode.run_id == run_id)).all()),
        )
        counts["run_graph_edges"] = _write_jsonl(
            db_dir / "run_graph_edges.jsonl",
            list(session.exec(select(RunGraphEdge).where(RunGraphEdge.run_id == run_id)).all()),
        )
        counts["run_graph_mutations"] = _write_jsonl(
            db_dir / "run_graph_mutations.jsonl",
            list(
                session.exec(
                    select(RunGraphMutation).where(RunGraphMutation.run_id == run_id)
                ).all()
            ),
        )
        counts["run_context_events"] = _write_jsonl(
            db_dir / "run_context_events.jsonl",
            list(
                session.exec(select(RunContextEvent).where(RunContextEvent.run_id == run_id)).all()
            ),
        )

    return counts


async def capture_dashboard(
    run_id: UUID,
    playwright_context: Any,  # slopcop: ignore[no-typing-any]
    out_dir: Path,
) -> dict[str, str]:
    """Screenshot the two dashboard pages that matter for a rollout.

    ``/`` — cohort index (confirms the run exists in the aggregate list).
    ``/run/<run_id>`` — run detail (agent graph, turn timeline, outputs).

    Returns a ``{page_name: screenshot_path}`` map.  Failures on either
    page are logged and the entry is omitted — a missing screenshot is
    itself useful rollout signal (dashboard regressed, or run not yet
    visible in index).
    """
    shots_dir = out_dir / "screenshots"
    captured: dict[str, str] = {}

    page = await playwright_context.new_page()
    try:
        await page.goto("/")
        await page.wait_for_load_state("networkidle")
        shot = shots_dir / "cohort_index.png"
        await page.screenshot(path=str(shot), full_page=True)
        captured["cohort_index"] = str(shot.relative_to(out_dir))
    except Exception:  # slopcop: ignore[no-broad-except]
        logger.exception("capture_dashboard: cohort_index screenshot failed")
    finally:
        await page.close()

    page = await playwright_context.new_page()
    try:
        await page.goto(f"/run/{run_id}")
        await page.wait_for_load_state("networkidle")
        shot = shots_dir / "run_detail.png"
        await page.screenshot(path=str(shot), full_page=True)
        captured["run_detail"] = str(shot.relative_to(out_dir))
    except Exception:  # slopcop: ignore[no-broad-except]
        logger.exception("capture_dashboard: run_detail screenshot failed for run_id=%s", run_id)
    finally:
        await page.close()

    return captured


def _fingerprint(value: str | None) -> str | None:
    """Short stable hash of a secret, for manifest provenance without leaking it."""
    if not value:
        return None
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def write_manifest(  # slopcop: ignore[max-function-params]
    out_dir: Path,
    *,
    run_id: UUID,
    benchmark: str,
    worker: str,
    evaluator: str,
    model: str,
    cli_returncode: int,
    terminal_state: dict[str, Any],  # slopcop: ignore[no-typing-any]
    started_at: datetime,
    finished_at: datetime,
    table_row_counts: dict[str, int],
    screenshots: dict[str, str],
    key_fingerprints: dict[str, str | None],
    budget_snapshot: dict[str, float] | None = None,
) -> Path:
    """Write ``manifest.json`` — the top-level index into the rollout."""
    manifest: dict[str, Any] = {  # slopcop: ignore[no-typing-any]
        "run_id": str(run_id),
        "benchmark": benchmark,
        "worker": worker,
        "evaluator": evaluator,
        "model": model,
        "cli_returncode": cli_returncode,
        "terminal_status": terminal_state.get("status"),
        "terminal_state": terminal_state,
        "wall_clock": {
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "duration_seconds": (finished_at - started_at).total_seconds(),
        },
        "db_row_counts": table_row_counts,
        "screenshots": screenshots,
        "key_fingerprints": key_fingerprints,
        "budget_snapshot": budget_snapshot,
    }
    path = out_dir / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2, default=str))
    return path


def write_report(out_dir: Path, manifest_path: Path) -> Path:
    """Stitch a short human/agent-readable summary from the manifest.

    This is the first thing a reviewing agent should open in a rollout
    directory — everything else is a drill-down.
    """
    manifest = json.loads(manifest_path.read_text())
    counts = manifest.get("db_row_counts", {})
    status = manifest.get("terminal_status", "unknown")
    duration = manifest.get("wall_clock", {}).get("duration_seconds")

    lines: list[str] = [
        f"# Rollout {manifest['run_id']}",
        "",
        f"- benchmark: `{manifest['benchmark']}`",
        f"- worker: `{manifest['worker']}`",
        f"- evaluator: `{manifest['evaluator']}`",
        f"- model: `{manifest['model']}`",
        f"- terminal status: **{status}**",
        f"- wall clock: {duration:.1f}s" if duration is not None else "- wall clock: unknown",
        f"- cli returncode: {manifest['cli_returncode']}",
        "",
        "## DB row counts",
        "",
    ]
    for table, n in sorted(counts.items()):
        lines.append(f"- `{table}`: {n}")
    lines.append("")
    shots = manifest.get("screenshots") or {}
    if shots:
        lines.append("## Screenshots")
        lines.append("")
        for name, rel in sorted(shots.items()):
            lines.append(f"- `{name}`: `{rel}`")
        lines.append("")

    lines.extend(
        [
            "## How to read this",
            "",
            "- `db/run_record.json` — one row.  `summary_json` carries the run-wide",
            "  outcome fields; `status`, `started_at`, `completed_at` anchor the timeline.",
            "- `db/run_generation_turns.jsonl` — every LLM turn in order.  Tool",
            "  calls + returns + thinking + text.  Read this to reconstruct what the",
            "  agent actually did.",
            "- `db/run_graph_nodes.jsonl` + `run_graph_mutations.jsonl` — agent's",
            "  subtask structure over time.",
            "- `db/run_task_evaluations.jsonl` — rubric scores, if the evaluator ran.",
            "- `db/sandbox_events.jsonl` — commands executed in the E2B sandbox.",
            "- `screenshots/` — what the dashboard renders for this run.",
        ]
    )

    path = out_dir / "report.md"
    path.write_text("\n".join(lines))
    return path
