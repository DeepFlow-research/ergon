"""Run/resume native MAG acceptance and retain inspectable per-sample evidence.

Use --stage contract first, then pilot, then catalog with the same output
folder. Completed pilots are reused only when code, model and limits match.
This submits ordinary Ergon samples; Ergon owns all task execution and retries.
"""

import argparse
import asyncio
import gzip
import json
import os
import platform
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from time import monotonic
from uuid import UUID, uuid4

from e2b import AsyncSandbox
from e2b.exceptions import SandboxNotFoundException
from ergon_builtins.benchmarks.manager_gym.inference import InferenceProfile
from ergon_builtins.benchmarks.manager_gym.rubric import definitions
from ergon_builtins.benchmarks.manager_gym.sample import make_manager_gym_sample
from ergon_builtins.benchmarks.manager_gym.state import (
    BENCHMARK_VERSION,
    SOURCE_REVISION,
    EpisodeConfig,
)
from ergon_builtins.benchmarks.manager_gym.upstream import SCENARIOS
from ergon_builtins.sandbox.e2b_sandbox import E2BSandbox
from ergon_core.api import Environment, Experiment, Sample, Task
from ergon_core.api.rubric.rubric import Rubric
from ergon_core.core.persistence.context.models import SampleContextEvent
from ergon_core.core.persistence.graph.models import SampleGraphEdge, SampleGraphNode
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.telemetry.models import (
    SampleRecord,
    SampleResource,
    SampleTaskAttempt,
    SampleTaskEvaluation,
    SandboxEvent,
    ThreadMessage,
)
from sqlmodel import select

from tests.fixtures.mag_contract import MAGContractCriterion, MAGContractWorker

PILOTS = (
    "legal_litigation_ediscovery",
    "icaap",
    "marketing_campaign",
    "banking_license_application",
)
TERMINAL = {"completed", "failed", "cancelled"}


def write_json(path: Path, value: object) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2, default=str) + "\n")
    temporary.replace(path)


def code_digest() -> str:
    root = Path(__file__).resolve().parents[3]
    digest = sha256()
    paths = sorted(
        p
        for directory in (
            "ergon_core/ergon_core",
            "ergon_core/migrations",
            "ergon_builtins/ergon_builtins",
            "examples/manager_gym",
            "tests/fixtures",
            "tests/real_llm/manager_gym",
        )
        for p in (root / directory).rglob("*.py")
    )
    for path in paths:
        digest.update(str(path.relative_to(root)).encode())
        digest.update(path.read_bytes())
    digest.update((root / "uv.lock").read_bytes())
    return digest.hexdigest()


def make_contract(name: str, model: str) -> Sample:
    return Sample.from_tasks(
        name="Native MAG contract",
        sample_key="contract",
        environment_name=name,
        tasks=[
            Task(
                task_slug="contract",
                instance_key="contract",
                description="Scripted native composition acceptance",
                worker=MAGContractWorker(
                    name="Contract coordinator", actor_key="manager_agent", model=model
                ),
                sandbox=E2BSandbox(timeout_seconds=3600),
                evaluators=(
                    Rubric(
                        name="Native contract",
                        criteria=(MAGContractCriterion(slug="native-contract"),),
                    ),
                ),
            )
        ],
    )


async def submit(scenario: str, args: argparse.Namespace) -> str:
    name = f"mag-{args.stage}-{scenario}-{uuid4().hex[:8]}"
    sample = (
        make_contract(name, args.model)
        if scenario == "contract"
        else make_manager_gym_sample(
            EpisodeConfig(
                scenario=scenario,
                seed=0,
                max_decisions=args.max_decisions,
                inference=InferenceProfile(thinking_token_budget=args.thinking_token_budget),
            ),
            environment_name=name,
            model=args.model,
        )
    )
    result = await Experiment(
        name=name,
        environments=[
            Environment.from_records(name=name, records=[sample], make_sample=lambda s: s)
        ],
    ).submit(k=1)
    return str(result.sample_ids[0])


def inspect_sample(sample_id: str) -> dict:
    key = UUID(sample_id)
    with get_session() as session:
        sample = session.get(SampleRecord, key)
        if sample is None:
            raise ValueError(f"Sample {key} does not exist")
        result: dict = {"sample": sample.model_dump(mode="json")}
        for name, model in (
            ("nodes", SampleGraphNode),
            ("edges", SampleGraphEdge),
            ("attempts", SampleTaskAttempt),
            ("evaluations", SampleTaskEvaluation),
            ("resources", SampleResource),
            ("messages", ThreadMessage),
            ("sandbox_events", SandboxEvent),
        ):
            result[name] = [
                r.model_dump(mode="json")
                for r in session.exec(select(model).where(model.sample_id == key)).all()
            ]
    return result


def named_report_matches_root(evidence: dict, name: str) -> bool:
    roots = {n["task_id"] for n in evidence["nodes"] if n["parent_task_id"] is None}
    attempts = [
        a for a in evidence["attempts"] if a["task_id"] in roots and a.get("worker_output_json")
    ]
    if len(attempts) != 1:
        return False
    attempt = attempts[0]
    reports = [
        r
        for r in evidence["resources"]
        if r["task_attempt_id"] == attempt["id"] and r["kind"] == "report" and r["name"] == name
    ]
    digest = sha256(attempt["worker_output_json"]["output"].encode()).hexdigest()
    return len(reports) == 1 and reports[0]["content_hash"] == digest


def score_checks(evidence: dict, scenario: str) -> dict:
    evaluations = evidence["evaluations"]
    if len(evaluations) != 1:
        return {"one_terminal_evaluation": False}
    evaluation = evaluations[0]
    summary = evaluation["summary_json"]
    if scenario == "contract":
        return {
            "native_contract": evaluation["score"] == 1,
            "criteria_saved": len(summary.get("criterion_results", [])) == 1,
            "contract_report_saved": named_report_matches_root(evidence, "mag-contract.json"),
        }
    rows = summary.get("criterion_results", [])
    expected = {d.slug for d in definitions(scenario)}
    scores, weights = {}, {}
    for row in rows:
        metadata = row.get("metadata", {})
        if metadata.get("kind") == "preference":
            owner = metadata["owner"]
            numerator, denominator = scores.get(owner, (0, 0))
            scores[owner] = (numerator + row["score"], denominator + row["max_score"])
            weights[owner] = metadata["preference_weight"]
    recomputed = sum(n / d * weights[owner] for owner, (n, d) in scores.items() if d)
    roots = {n["task_id"] for n in evidence["nodes"] if n["parent_task_id"] is None}
    root = next(
        (
            a.get("worker_output_json")
            for a in evidence["attempts"]
            if a["task_id"] in roots and a.get("worker_output_json")
        ),
        None,
    )
    # Hash the stored JSON itself so later schema defaults cannot rewrite the
    # identity of historical evidence when it is inspected/exported.
    digest = (
        sha256(
            json.dumps(json.loads(root["output"]), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        if root
        else None
    )
    return {
        "all_criteria_saved": len(rows) == len(expected)
        and {r["criterion_slug"] for r in rows} == expected,
        "numeric_complete_evaluation": evaluation["score"] is not None
        and not summary.get("metadata", {}).get("incomplete", False),
        "utility_recomputes": evaluation["score"] is not None
        and abs(recomputed - evaluation["score"]) < 1e-9,
        "one_frozen_snapshot": bool(rows)
        and {r.get("metadata", {}).get("snapshot_hash") for r in rows} == {digest},
        "snapshot_report_saved": named_report_matches_root(evidence, "manager-gym-snapshot.json"),
        "native_team_work": any(
            a["task_id"] not in roots and a.get("worker_output_json") and a["status"] == "completed"
            for a in evidence["attempts"]
        ),
    }


def execution_checks(evidence: dict) -> dict[str, bool]:
    roots = [n for n in evidence["nodes"] if n["parent_task_id"] is None]
    failed = {n["task_id"] for n in evidence["nodes"] if n["status"] == "failed"}
    latest = {}
    for attempt in sorted(evidence["attempts"], key=lambda a: (a["created_at"], a["id"])):
        latest[attempt["task_id"]] = attempt
    accounted = set()
    for task_id in failed:
        output = latest.get(task_id, {}).get("worker_output_json") or {}
        failure = output.get("metadata", {}).get("model_failure", {})
        if output.get("success") is False and failure.get("kind") in {
            "request_limit",
            "output_validation",
        }:
            accounted.add(task_id)
    return {
        "sample_terminal": evidence["sample"]["status"] in {"completed", "failed"},
        "native_failures_accounted": failed == accounted,
        "manager_completed": bool(roots) and all(n["status"] == "completed" for n in roots),
        "all_tasks_terminal": all(n["status"] in TERMINAL for n in evidence["nodes"]),
    }


async def closed_sandboxes(evidence: dict) -> dict[str, bool]:
    ids = {e["sandbox_id"] for e in evidence["sandbox_events"] if e["kind"] == "sandbox_created"}
    ids.update(a["sandbox_id"] for a in evidence["attempts"] if a.get("sandbox_id"))
    result = {}
    for sandbox_id in sorted(ids):
        try:
            await AsyncSandbox.get_info(sandbox_id, request_timeout=15)
            result[sandbox_id] = False
        except SandboxNotFoundException:
            result[sandbox_id] = True
    return result


def export_evidence(folder: Path, sample_id: str, evidence: dict) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    write_json(folder / "records.json", evidence)
    with get_session() as session, gzip.open(folder / "context.jsonl.gz", "wt") as output:
        for row in session.exec(
            select(SampleContextEvent).where(SampleContextEvent.sample_id == UUID(sample_id))
        ).all():
            output.write(row.model_dump_json() + "\n")
    artifacts = folder / "artifacts"
    artifacts.mkdir(exist_ok=True)
    for resource in evidence["resources"]:
        path = Path(resource["file_path"])
        if path.is_file():
            data = path.read_bytes()
            if (
                resource.get("content_hash")
                and sha256(data).hexdigest() != resource["content_hash"]
            ):
                raise ValueError(f"Artifact digest mismatch: {resource['id']}")
            (artifacts / str(resource["id"])).write_bytes(data)
        elif not resource.get("error"):
            raise FileNotFoundError(f"Missing retained artifact {resource['id']}")


async def finish(sample_id: str, scenario: str, folder: Path) -> dict:
    evidence = inspect_sample(sample_id)
    cleanup = {}
    for _ in range(13):
        cleanup = await closed_sandboxes(evidence)
        if cleanup and all(cleanup.values()):
            break
        await asyncio.sleep(5)
    checks = score_checks(evidence, scenario)
    checks.update(execution_checks(evidence))
    checks.update(
        artifacts_saved=any(
            not resource["name"].startswith(".checkpoints/") for resource in evidence["resources"]
        ),
        owned_sandboxes_closed=bool(cleanup) and all(cleanup.values()),
    )
    evidence["checks"] = checks
    evidence["sandbox_checks"] = cleanup
    export_evidence(folder / sample_id, sample_id, evidence)
    return {
        "sample_id": sample_id,
        "scenario": scenario,
        "accepted": all(checks.values()),
        "checks": checks,
        "score": evidence["evaluations"][0]["score"] if evidence["evaluations"] else None,
        "task_count": len(evidence["nodes"]),
        "message_count": len(evidence["messages"]),
        "resource_count": len(evidence["resources"]),
    }


STAGES = ("contract", "pilot", "catalog")
POLL_SECONDS = 5


def stage_scenarios(stage: str) -> list[str]:
    """Scenarios a stage runs: the scripted contract, four pilots, or the catalog."""
    return {"contract": ["contract"], "pilot": list(PILOTS), "catalog": list(SCENARIOS)}[stage]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=STAGES, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-decisions", type=int, default=50)
    parser.add_argument(
        "--model",
        default=os.environ.get("ERGON_MAG_MODEL"),
        required=not os.environ.get("ERGON_MAG_MODEL"),
        help="Ergon model target for every role and the judge (default: $ERGON_MAG_MODEL).",
    )
    parser.add_argument(
        "--thinking-token-budget",
        type=int,
        help="Reasoning token cap for thinking models served by vLLM.",
    )
    parser.add_argument("--concurrency", type=int, choices=[1, 2], default=2)
    parser.add_argument("--timeout-seconds", type=int, default=5400)
    return parser.parse_args()


def load_ledger(path: Path, args: argparse.Namespace) -> dict:
    """Resume the ledger in ``path``, refusing one recorded under other settings."""
    configuration = {
        "code_digest": code_digest(),
        "model": args.model,
        "max_decisions": args.max_decisions,
        "thinking_token_budget": args.thinking_token_budget,
        "seed": 0,
        "benchmark_version": BENCHMARK_VERSION,
        "source_revision": SOURCE_REVISION,
    }
    if not path.exists():
        return {
            "configuration": configuration,
            "machine": platform.platform(),
            "started_at": datetime.now(UTC).isoformat(),
            "samples": {},
        }
    ledger = json.loads(path.read_text())
    if ledger["configuration"] != configuration:
        raise ValueError(
            "Output folder belongs to a different code/model/configuration; use a new folder"
        )
    return ledger


async def collect_finished(
    active: dict[str, str], ledger: dict, ledger_path: Path, folder: Path
) -> None:
    """Record every active sample that reached a terminal status."""
    for scenario, sample_id in list(active.items()):
        evidence = inspect_sample(sample_id)
        if not execution_checks(evidence)["native_failures_accounted"]:
            ledger["admission_failure"] = sample_id
            write_json(ledger_path, ledger)
        if evidence["sample"]["status"] in TERMINAL:
            ledger["samples"][scenario] = await finish(sample_id, scenario, folder)
            write_json(ledger_path, ledger)
            print(json.dumps(ledger["samples"][scenario]), flush=True)
            del active[scenario]


async def main() -> None:
    args = parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    ledger_path = args.output / "acceptance.json"
    ledger = load_ledger(ledger_path, args)
    scenarios = stage_scenarios(args.stage)
    pending = [s for s in scenarios if s not in ledger["samples"]]
    active = {
        s: r["sample_id"]
        for s, r in ledger["samples"].items()
        if s in scenarios and "accepted" not in r
    }
    deadline = monotonic() + args.timeout_seconds
    while pending or active:
        await collect_finished(active, ledger, ledger_path, args.output)
        # Stop admitting new samples after any failure; admitted ones still drain.
        if ledger.get("admission_failure") or any(
            ledger["samples"].get(scenario, {}).get("accepted") is False for scenario in scenarios
        ):
            pending.clear()
        while pending and len(active) < args.concurrency:
            scenario = pending.pop(0)
            sample_id = await submit(scenario, args)
            active[scenario] = sample_id
            ledger["samples"][scenario] = {"sample_id": sample_id}
            write_json(ledger_path, ledger)
            print(json.dumps({"submitted": scenario, "sample_id": sample_id}), flush=True)
        if monotonic() > deadline:
            raise TimeoutError(
                "Acceptance deadline; existing sample ids retained for inspection/resume"
            )
        if active:
            await asyncio.sleep(POLL_SECONDS)
    if not all(ledger["samples"].get(s, {}).get("accepted") for s in scenarios):
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
