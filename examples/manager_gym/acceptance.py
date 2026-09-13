"""Run/resume native MAG acceptance and retain inspectable per-sample evidence.

Use --stage contract first, then pilot, then catalog with the same output
folder. Completed pilots are reused only when code, model and limits match.
This submits ordinary Ergon samples; Ergon owns all task execution and retries.
"""

import argparse
import asyncio
from datetime import UTC, datetime
import gzip
from hashlib import sha256
import json
from pathlib import Path
import platform
from time import monotonic
from uuid import UUID, uuid4

from e2b import AsyncSandbox
from e2b.exceptions import SandboxNotFoundException
from sqlmodel import select

from ergon_core.api import Environment, Experiment, Sample, Task
from ergon_core.api.rubric.rubric import Rubric
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.graph.models import SampleGraphNode, SampleGraphEdge
from ergon_core.core.persistence.context.models import SampleContextEvent
from ergon_core.core.persistence.telemetry.models import (
    SampleRecord,
    SampleTaskAttempt,
    SampleTaskEvaluation,
    SampleResource,
    ThreadMessage,
    SandboxEvent,
)
from ergon_builtins.sandbox.e2b_sandbox import E2BSandbox
from ergon_builtins.benchmarks.manager_gym.inference import INTERNAL_MODEL, require_internal_model
from ergon_builtins.benchmarks.manager_gym.sample import make_manager_gym_sample
from ergon_builtins.benchmarks.manager_gym.scenario_catalog import SCENARIOS
from ergon_builtins.benchmarks.manager_gym.state import (
    EpisodeConfig,
    BENCHMARK_VERSION,
    SOURCE_REVISION,
)
from ergon_builtins.benchmarks.manager_gym.rubric import definitions
from tests.fixtures.mag_contract import MAGContractWorker, MAGContractCriterion

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
    root = Path(__file__).resolve().parents[2]
    digest = sha256()
    paths = sorted(
        p
        for directory in (
            "ergon_core/ergon_core",
            "ergon_builtins/ergon_builtins",
            "tests/fixtures",
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
            EpisodeConfig(scenario=scenario, seed=0, max_decisions=args.max_decisions),
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
        "native_team_work": any(
            a["task_id"] not in roots and a.get("worker_output_json") and a["status"] == "completed"
            for a in evidence["attempts"]
        ),
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
    checks.update(
        sample_completed=evidence["sample"]["status"] == "completed",
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


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=["contract", "pilot", "catalog"], required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-decisions", type=int, default=50)
    parser.add_argument("--model", default=INTERNAL_MODEL)
    parser.add_argument("--concurrency", type=int, choices=[1, 2], default=2)
    parser.add_argument("--timeout-seconds", type=int, default=5400)
    args = parser.parse_args()
    require_internal_model(args.model)
    args.output.mkdir(parents=True, exist_ok=True)
    ledger_path = args.output / "acceptance.json"
    configuration = {
        "code_digest": code_digest(),
        "model": args.model,
        "max_decisions": args.max_decisions,
        "seed": 0,
        "benchmark_version": BENCHMARK_VERSION,
        "source_revision": SOURCE_REVISION,
    }
    ledger: dict = (
        json.loads(ledger_path.read_text())
        if ledger_path.exists()
        else {
            "configuration": configuration,
            "machine": platform.platform(),
            "started_at": datetime.now(UTC).isoformat(),
            "samples": {},
        }
    )
    if ledger["configuration"] != configuration:
        raise ValueError(
            "Output folder belongs to a different code/model/configuration; use a new folder"
        )
    scenarios = (
        ["contract"]
        if args.stage == "contract"
        else list(PILOTS)
        if args.stage == "pilot"
        else list(SCENARIOS)
    )
    pending = [s for s in scenarios if s not in ledger["samples"]]
    active = {
        s: r["sample_id"]
        for s, r in ledger["samples"].items()
        if s in scenarios and "accepted" not in r
    }
    deadline = monotonic() + args.timeout_seconds
    while pending or active:
        while pending and len(active) < args.concurrency:
            scenario = pending.pop(0)
            sample_id = await submit(scenario, args)
            active[scenario] = sample_id
            ledger["samples"][scenario] = {"sample_id": sample_id}
            write_json(ledger_path, ledger)
            print(json.dumps({"submitted": scenario, "sample_id": sample_id}), flush=True)
        for scenario, sample_id in list(active.items()):
            evidence = inspect_sample(sample_id)
            if evidence["sample"]["status"] in TERMINAL:
                ledger["samples"][scenario] = await finish(sample_id, scenario, args.output)
                write_json(ledger_path, ledger)
                print(json.dumps(ledger["samples"][scenario]), flush=True)
                del active[scenario]
        if monotonic() > deadline:
            raise TimeoutError(
                "Acceptance deadline; existing sample ids retained for inspection/resume"
            )
        if active:
            await asyncio.sleep(5)
    if not all(ledger["samples"][s]["accepted"] for s in scenarios):
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
